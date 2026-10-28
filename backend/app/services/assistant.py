"""Asistente IA de consultas (Gemini, Google AI Studio).

Solo LEE: en cada pregunta arma una foto en texto de los datos de las cuentas del
emprendimiento (ASSISTANT_USERS) y se la pasa al modelo como contexto, junto con la
conversación. No guarda nada ni cambia nada de la app.

Los totales (por mes, cuenta, fuente, cliente) se calculan aquí y no se le piden al modelo:
sumar cientos de filas a mano es justo donde un modelo de lenguaje se equivoca.
"""
import json
import logging
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.constants import LABOR_RATE_PER_HOUR, ELECTRICITY_RATE, MARGIN_SCENARIOS, RISK_LEVELS
from app.models.company_expense import CompanyExpense
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.quote import Quote
from app.models.sale import STATUS_CANCELLED, STATUS_DELIVERED, Sale
from app.models.sale_filament import SaleFilament
from app.models.supply import Supply
from app.models.user import User
from app.models.warehouse_item import WarehouseItem

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SECONDS = 60
NOTES_MAX = 140

STATUS_LABELS = {
    "pendiente": "Pendiente",
    "en_produccion": "En producción",
    "lista": "Lista",
    "entregada": "Entregada",
    "cancelado": "Cancelado",
}
PAYMENT_LABELS = {
    "efectivo": "Efectivo",
    "transferencia": "Transferencia",
    "debito": "Débito",
    "credito": "Crédito",
    "por_cobrar": "Por cobrar",
    "cortesia": "Cortesía (regalo)",
}


class AssistantError(Exception):
    """Error con un mensaje apto para mostrarle al usuario."""


def can_use_assistant(user: User) -> bool:
    return user.username.lower() in settings.assistant_users_set


# ---------------------------------------------------------------------------
# Contexto: foto de los datos en texto
# ---------------------------------------------------------------------------


def _n(value: Decimal | None) -> str:
    """Número sin ceros de más (CLP sin decimales cuando son enteros)."""
    if value is None:
        return "-"
    value = Decimal(value)
    return f"{value:.0f}" if value == value.to_integral_value() else f"{value:.2f}"


def _clean(text: str | None, limit: int = NOTES_MAX) -> str:
    if not text:
        return ""
    text = " ".join(text.split()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _filament_name(f: Filament) -> str:
    return f"{f.brand} {f.type} {f.color}"


def _sale_materials(sale: Sale) -> str:
    if sale.filaments_used:
        return ", ".join(f"{_filament_name(sf.filament)} {_n(sf.grams_used)}g" for sf in sale.filaments_used)
    if sale.filament:
        return f"{_filament_name(sale.filament)} {_n(sale.grams_used)}g"
    return ""


class _Totals:
    def __init__(self):
        self.count = 0
        self.revenue = Decimal(0)
        self.cost = Decimal(0)
        self.profit = Decimal(0)

    def add(self, sale: Sale):
        self.count += 1
        self.revenue += sale.total_price
        self.cost += sale.total_cost
        self.profit += sale.profit

    def row(self, label: str) -> str:
        return f"{label} | {self.count} | {_n(self.revenue)} | {_n(self.cost)} | {_n(self.profit)}"


def _summaries(sales: list[Sale]) -> list[str]:
    delivered = [s for s in sales if s.status == STATUS_DELIVERED and s.delivered_date]
    by_month, by_account, by_source, by_payment, by_client = (defaultdict(_Totals) for _ in range(5))
    for s in delivered:
        by_month[s.delivered_date.strftime("%Y-%m")].add(s)
        by_account[s.owner.username].add(s)
        by_source[s.sale_source or "sin_registrar"].add(s)
        by_payment[PAYMENT_LABELS.get(s.payment_method, s.payment_method)].add(s)
        by_client[s.client_name.strip().title()].add(s)

    header = "clave | pedidos | ingresos | costos | ganancia"
    out = ["## Resúmenes precalculados (solo pedidos ENTREGADOS, por fecha de entrega; usa estos números)"]
    for title, data, key in (
        ("Por mes", by_month, lambda kv: kv[0]),
        ("Por cuenta dueña del inventario", by_account, lambda kv: -kv[1].revenue),
        ("Por fuente de venta", by_source, lambda kv: -kv[1].revenue),
        ("Por medio de pago", by_payment, lambda kv: -kv[1].revenue),
    ):
        out += [f"### {title}", header, *(t.row(k) for k, t in sorted(data.items(), key=key))]
    out += [f"### Clientes (top 40 por ingresos, de {len(by_client)} clientes distintos)", header]
    out += [t.row(k) for k, t in sorted(by_client.items(), key=lambda kv: -kv[1].revenue)[:40]]

    open_orders = [s for s in sales if s.status not in (STATUS_DELIVERED, STATUS_CANCELLED)]
    cancelled = [s for s in sales if s.status == STATUS_CANCELLED]
    total = _Totals()
    for s in delivered:
        total.add(s)
    out += [
        "### Totales",
        f"Entregados (histórico): {total.count} pedidos, ingresos {_n(total.revenue)}, costos {_n(total.cost)}, "
        f"ganancia {_n(total.profit)}",
        f"Pedidos abiertos (pendiente/en producción/lista): {len(open_orders)}, "
        f"por {_n(sum((s.total_price for s in open_orders), Decimal(0)))}",
        f"Por cobrar (entregados sin pagar): "
        f"{_n(sum((s.total_price for s in delivered if s.payment_method == 'por_cobrar'), Decimal(0)))}",
        f"Cancelados: {len(cancelled)}, pérdida total {_n(sum((s.loss_amount for s in cancelled), Decimal(0)))}",
    ]
    return out


def build_context(db: Session) -> str:
    names = settings.assistant_users_set
    users = [u for u in db.query(User).all() if u.username.lower() in names]
    ids = [u.id for u in users]
    usernames = {u.id: u.username for u in users}

    sales = (
        db.query(Sale)
        .options(
            selectinload(Sale.owner),
            selectinload(Sale.created_by),
            selectinload(Sale.printer),
            selectinload(Sale.filament),
            selectinload(Sale.filaments_used).selectinload(SaleFilament.filament),
        )
        .filter(or_(Sale.user_id.in_(ids), Sale.created_by_user_id.in_(ids)))
        .order_by(Sale.sale_date, Sale.created_at)
        .all()
    )

    out = [f"Fecha de hoy: {date.today().isoformat()}. Moneda: pesos chilenos (CLP)."]

    out += ["## Cuentas"]
    for u in users:
        kind = "cuenta de la Empresa (observador con inventario propio)" if u.is_company else f"rol {u.role.name}"
        out.append(f"- {u.username}: {kind}")

    out += ["## Impresoras", "dueño | nombre | valor compra | horas usadas | vida útil h | kW | activa"]
    for p in db.query(Printer).filter(Printer.user_id.in_(ids)).order_by(Printer.name):
        out.append(f"{usernames[p.user_id]} | {p.name} | {_n(p.purchase_value)} | {_n(p.hours_used)} | "
                   f"{_n(p.lifetime_hours)} | {p.power_kw} | {'sí' if p.is_active else 'no'}")

    out += ["## Filamentos", "dueño | marca tipo color | disponible g | usado g | alerta mín g | precio carrete | activo"]
    for f in db.query(Filament).filter(Filament.user_id.in_(ids)).order_by(Filament.brand, Filament.type):
        out.append(f"{usernames[f.user_id]} | {_filament_name(f)} | {_n(f.available_g)} | {_n(f.used_g)} | "
                   f"{_n(f.min_alert_g)} | {_n(f.spool_price)} | {'sí' if f.is_active else 'no'}")

    out += ["## Insumos", "dueño | nombre | categoría | cantidad | costo unitario | alerta mín | activo"]
    for s in db.query(Supply).filter(Supply.user_id.in_(ids)).order_by(Supply.name):
        out.append(f"{usernames[s.user_id]} | {s.name} | {s.category} | {_n(s.quantity_available)} | "
                   f"{_n(s.unit_cost)} | {_n(s.min_alert_qty)} | {'sí' if s.is_active else 'no'}")

    out += _summaries(sales)

    out += [
        f"## Pedidos/ventas ({len(sales)}, todos los estados)",
        "fecha pedido | fecha comprometida | fecha entrega | estado | dueño | registró | cliente | comprador | "
        "precio | costo | ganancia | margen % | pago | fuente | impresora | horas impresión | materiales | "
        "envío | notas",
    ]
    for s in sales:
        status = STATUS_LABELS.get(s.status, s.status)
        if s.status == STATUS_CANCELLED:
            status += f" (motivo: {_clean(s.cancel_reason, 80)}; pérdida {_n(s.loss_amount)})"
        out.append(" | ".join([
            s.sale_date.isoformat(),
            s.promised_delivery_date.isoformat(),
            s.delivered_date.isoformat() if s.delivered_date else "",
            status,
            s.owner.username,
            s.created_by.username if s.created_by else "",
            _clean(s.client_name, 60),
            _clean(s.buyer_name, 60),
            _n(s.total_price), _n(s.total_cost), _n(s.profit), _n(s.margin_percent),
            PAYMENT_LABELS.get(s.payment_method, s.payment_method),
            s.sale_source or "",
            s.printer.name,
            _n(s.print_hours),
            _sale_materials(s),
            f"{_n(s.shipping_cost)} ({s.delivery_by})" if s.shipping_cost else "",
            _clean(s.notes),
        ]))

    quotes = (
        db.query(Quote).options(selectinload(Quote.items))
        .filter(Quote.user_id.in_(ids)).order_by(Quote.quote_date).all()
    )
    out += [f"## Cotizaciones ({len(quotes)})", "cuenta | n° | fecha | cliente | total | ítems"]
    for q in quotes:
        items = "; ".join(f"{_n(i.quantity)}x {_clean(i.description, 60)} ({_n(i.unit_price)})" for i in q.items)
        out.append(f"{usernames[q.user_id]} | {q.quote_number} | {q.quote_date} | {_clean(q.client_name, 60)} | "
                   f"{_n(q.total)} | {items}")

    pieces = db.query(WarehouseItem).filter(WarehouseItem.user_id.in_(ids)).order_by(WarehouseItem.entry_date).all()
    out += [f"## Almacén (piezas de pedidos cancelados, {len(pieces)})", "dueño | pieza | ingreso | costo | precio | estado"]
    for w in pieces:
        out.append(f"{usernames[w.user_id]} | {_clean(w.name, 60)} | {w.entry_date} | {_n(w.cost)} | "
                   f"{_n(w.price)} | {w.status}")

    expenses = db.query(CompanyExpense).order_by(CompanyExpense.expense_date).all()
    out += [f"## Gastos de la Empresa ({len(expenses)})", "fecha | concepto | monto | pagó"]
    out += [f"{e.expense_date} | {_clean(e.concept, 80)} | {_n(e.amount)} | {e.paid_by}" for e in expenses]

    return "\n".join(out)


def _system_prompt(user: User, context: str) -> str:
    margins = ", ".join(f"{m['label']} {m['margin_percent']}%" for m in MARGIN_SCENARIOS)
    risks = ", ".join(f"{k} {v}%" for k, v in RISK_LEVELS.items())
    return f"""Eres el asistente de Zola, la app de gestión de un emprendimiento de impresión 3D en Chile.
Hablas con {user.username}, uno de los dueños. Responde en español, breve y directo, con montos en CLP
con separador de miles (ej. $12.500). Usa listas o tablas cortas en Markdown cuando ayuden.

Cómo funciona Zola:
- Calculadora: costo = material (filamento) + depreciación de la impresora + luz ({_n(ELECTRICITY_RATE)} CLP/kWh)
  + postprocesado ({_n(LABOR_RATE_PER_HOUR)} CLP/h) + insumos. Márgenes: {margins}. Riesgo de fallo
  (reserva sobre el costo de producción): {risks}.
- Pedidos: Pendiente → En producción → Lista → Entregada, o Cancelado. Los ingresos y la ganancia se
  cuentan por FECHA DE ENTREGA y solo con pedidos Entregados. "Por cobrar" = entregado sin pagar.
  "Cortesía" = regalo (no entra dinero).
- Cada venta tiene un "dueño" (la cuenta cuyo inventario se usó) y quien la "registró".
- Simple_Solutions3D es la cuenta de la Empresa; Diego y Sntg son socios.
- Almacén: piezas de pedidos cancelados que se pueden revender. Gastos de la Empresa: compras de la Caja.

Reglas:
- Responde SOLO con los datos de abajo. Si algo no está, dilo; no inventes cifras ni clientes.
- Para totales usa los resúmenes precalculados. Si tienes que calcular algo nuevo, hazlo con cuidado
  y aclara de qué filas sale.
- Solo consultas: no puedes crear, editar ni borrar nada en la app; si te lo piden, explica dónde hacerlo.

# DATOS DE ZOLA
{context}"""


# ---------------------------------------------------------------------------
# Llamada a Gemini
# ---------------------------------------------------------------------------


def _gemini_error(status: int, body: str) -> AssistantError:
    logger.warning("Gemini respondió %s: %s", status, body[:500])
    if status == 429:
        return AssistantError("Se alcanzó el límite de consultas de Gemini. Espera un minuto y vuelve a intentar.")
    if status in (401, 403) or "API_KEY_INVALID" in body or "API key not valid" in body:
        return AssistantError("La clave de Gemini (GEMINI_API_KEY) no es válida o no tiene permisos.")
    if status == 404:
        return AssistantError(f"El modelo '{settings.gemini_model}' no existe. Revisa GEMINI_MODEL.")
    return AssistantError("Gemini no pudo responder ahora. Intenta de nuevo en unos segundos.")


def ask(db: Session, user: User, messages: list[dict]) -> str:
    """messages: [{"role": "user"|"assistant", "text": str}, ...], la última es la pregunta."""
    if not settings.gemini_api_key:
        raise AssistantError("El asistente aún no está configurado: falta GEMINI_API_KEY en el servidor.")

    payload = {
        "system_instruction": {"parts": [{"text": _system_prompt(user, build_context(db))}]},
        "contents": [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["text"]}]}
            for m in messages
        ],
        "generationConfig": {"temperature": 0.2},
    }
    request = urllib.request.Request(
        GEMINI_URL.format(model=settings.gemini_model),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _gemini_error(exc.code, exc.read().decode("utf-8", "replace")) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("No se pudo contactar a Gemini: %s", exc)
        raise AssistantError("No se pudo contactar a Gemini. Intenta de nuevo en unos segundos.") from exc

    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        logger.warning("Gemini respondió sin texto: %s", json.dumps(data)[:500])
        raise AssistantError("Gemini no devolvió respuesta para esa pregunta. Prueba reformulándola.")
    return text
