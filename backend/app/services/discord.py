"""Avisos de pedidos en Discord (webhook).

Cada pedido agendado por un usuario de DISCORD_NOTIFY_USERS se anuncia con una tarjeta, y
esa misma tarjeta se edita cuando el pedido cambia: verde mientras está abierto, roja al
entregarse, gris si se cancela o elimina.

Todo corre en segundo plano (BackgroundTasks), con su propia sesión de base de datos, y
nunca lanza: si Discord o la tabla discord_messages fallan, el pedido no se entera.
"""
import json
import logging
import re
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.config import settings
from app.database import SessionLocal
from app.models.discord_message import DiscordMessage
from app.models.sale import (
    STATUS_CANCELLED,
    STATUS_DELIVERED,
    STATUS_IN_PRODUCTION,
    STATUS_PENDING,
    STATUS_READY,
    Sale,
)
from app.schemas.sale import SaleResponse
from app.services.sale_builder import to_sale_response

logger = logging.getLogger(__name__)

GREEN = 0x2ECC71
RED = 0xE74C3C
GREY = 0x80848E
# Estado que no existe en la app: el pedido se borró y la tarjeta queda como constancia.
DELETED = "eliminado"

# Components V2 de Discord (https://discord.com/developers/docs/components/reference).
IS_COMPONENTS_V2 = 1 << 15
ACTION_ROW, BUTTON, SECTION, TEXT, THUMBNAIL, SEPARATOR, CONTAINER = 1, 2, 9, 10, 11, 14, 17
LINK_BUTTON = 5


@dataclass(frozen=True)
class Theme:
    color: int
    kicker: str
    badge: str


THEMES = {
    STATUS_PENDING: Theme(GREEN, "🆕 NUEVO PEDIDO", "🟢 **Pendiente**"),
    STATUS_IN_PRODUCTION: Theme(GREEN, "🛠️ EN PRODUCCIÓN", "🟢 **En producción**"),
    STATUS_READY: Theme(GREEN, "📦 LISTO PARA ENTREGAR", "🟢 **Lista**"),
    STATUS_DELIVERED: Theme(RED, "✅ PEDIDO ENTREGADO", "🔴 **Entregada**"),
    STATUS_CANCELLED: Theme(GREY, "🚫 PEDIDO CANCELADO", "⚫ **Cancelado**"),
    DELETED: Theme(GREY, "🗑️ PEDIDO ELIMINADO", "⚫ **Eliminado**"),
}
PROGRESS = (
    (STATUS_PENDING, "Pendiente"),
    (STATUS_IN_PRODUCTION, "Producción"),
    (STATUS_READY, "Lista"),
    (STATUS_DELIVERED, "Entregada"),
)


# ---------------------------------------------------------------------------
# Tareas en segundo plano (lo que llaman los routers)
# ---------------------------------------------------------------------------


def announce_order(sale_id: uuid.UUID) -> None:
    """Publica la tarjeta de un pedido recién creado, si lo agendó un usuario de la lista."""
    if not settings.discord_webhook_url:
        return
    try:
        with SessionLocal() as db:
            sale = db.get(Sale, sale_id)
            if sale is None or sale.created_by is None:
                return
            if sale.created_by.username.lower() not in settings.discord_notify_users_set:
                return
            message_id = _deliver(to_sale_response(sale))
            if message_id:
                db.add(DiscordMessage(sale_id=sale_id, message_id=message_id))
                db.commit()
    except Exception:
        logger.exception("No se pudo anunciar el pedido %s en Discord", sale_id)


def sync_order(sale_id: uuid.UUID) -> None:
    """Actualiza la tarjeta de un pedido ya anunciado con su estado actual. Lee el pedido
    al momento de correr, así dos cambios seguidos siempre dejan el último."""
    if not settings.discord_webhook_url:
        return
    try:
        with SessionLocal() as db:
            link = db.get(DiscordMessage, sale_id)
            sale = db.get(Sale, sale_id) if link is not None else None
            if sale is None:
                return
            _edit_or_forget(db, link, to_sale_response(sale))
    except Exception:
        logger.exception("No se pudo actualizar el pedido %s en Discord", sale_id)


def snapshot_before_delete(sale: Sale) -> SaleResponse | None:
    """Foto del pedido justo antes de eliminarlo (corre dentro de la request: nunca lanza)."""
    if not settings.discord_webhook_url:
        return None
    try:
        return to_sale_response(sale)
    except Exception:
        logger.exception("No se pudo preparar el aviso de eliminación del pedido %s", sale.id)
        return None


def mark_order_deleted(sale_id: uuid.UUID, snapshot: SaleResponse | None) -> None:
    """El pedido se eliminó: su tarjeta queda en gris como constancia y se suelta el vínculo."""
    if not settings.discord_webhook_url or snapshot is None:
        return
    try:
        with SessionLocal() as db:
            link = db.get(DiscordMessage, sale_id)
            if link is None:
                return
            _edit_or_forget(db, link, snapshot.model_copy(update={"status": DELETED}))
            if db.get(DiscordMessage, sale_id) is not None:
                db.delete(link)
                db.commit()
    except Exception:
        logger.exception("No se pudo marcar como eliminado el pedido %s en Discord", sale_id)


def _edit_or_forget(db, link: DiscordMessage, sale: SaleResponse) -> None:
    try:
        _deliver(sale, message_id=link.message_id)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        # Alguien borró el mensaje en Discord: no hay nada más que editar.
        db.delete(link)
        db.commit()


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------


def _deliver(sale: SaleResponse, message_id: str | None = None) -> str | None:
    """Publica (o edita) la tarjeta. Primero con Components V2; si Discord no lo acepta
    (400), cae al embed clásico para que el aviso nunca se pierda. Devuelve el id."""
    base, _, query = settings.discord_webhook_url.partition("?")
    params = dict(parse_qsl(query))  # ej. thread_id, si el webhook apunta a un hilo
    target = base.rstrip("/") if message_id is None else f"{base.rstrip('/')}/messages/{message_id}"
    method = "POST" if message_id is None else "PATCH"
    if message_id is None:
        params["wait"] = "true"  # que Discord devuelva el mensaje, para guardar su id
    try:
        data = _request(method, f"{target}?{urlencode({**params, 'with_components': 'true'})}", _v2_payload(sale))
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        logger.warning("Discord rechazó la tarjeta Components V2 (%s); se envía como embed", exc.read()[:500])
        data = _request(method, f"{target}?{urlencode(params)}".rstrip("?"), _embed_payload(sale))
    return str(data["id"]) if data and "id" in data else None


def _request(method: str, url: str, payload: dict) -> dict | None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        # Discord (Cloudflare) rechaza con 403 el User-Agent por defecto de urllib.
        headers={"Content-Type": "application/json", "User-Agent": "SS3D-Notifier/1.0"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        body = response.read()
    return json.loads(body) if body else None


# ---------------------------------------------------------------------------
# Diseño de la tarjeta
# ---------------------------------------------------------------------------

# Cada línea empieza con un emoji, así que #, > y - del usuario nunca quedan al inicio.
_MARKDOWN = re.compile(r"([\\*_~`|\[\]<])")


def _esc(text: str, limit: int) -> str:
    """Texto escrito por el usuario: sin formato Markdown accidental y con largo acotado."""
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return _MARKDOWN.sub(r"\\\1", text)


def _money(value) -> str:
    return f"${value:,.0f}".replace(",", ".")


def _ts(day: date) -> int:
    # Mediodía UTC-3: cae en el día correcto en Chile todo el año. Discord muestra <t:...>
    # en la zona horaria de quien lo lee.
    return int(datetime(day.year, day.month, day.day, 15, tzinfo=timezone.utc).timestamp())


def _logo() -> str | None:
    # Servido por Vercel desde frontend/public/img/Logo1.jpg (versión grande y nítida del logo).
    return f"{settings.app_url.rstrip('/')}/img/Logo1.jpg" if settings.app_url else None


def _calendar_url() -> str | None:
    return f"{settings.app_url.rstrip('/')}/calendario" if settings.app_url else None


def _header(s: SaleResponse) -> str:
    theme = THEMES[s.status]
    name = _esc(s.client_name, 120)
    if s.status in (STATUS_CANCELLED, DELETED):
        name = f"~~{name}~~"
    return f"-# {theme.kicker}  ·  #{s.id.hex[:6].upper()}\n## 📦 {name}\n{theme.badge}"


def _details(s: SaleResponse) -> str:
    lines = []
    if s.status == STATUS_DELIVERED and s.delivered_date:
        lines.append(f"🗓️ **Entregado:** <t:{_ts(s.delivered_date)}:D>")
    elif s.status in (STATUS_CANCELLED, DELETED):
        lines.append(f"🗓️ **Entrega:** ~~<t:{_ts(s.promised_delivery_date)}:D>~~")
    else:
        ts = _ts(s.promised_delivery_date)
        lines.append(f"🗓️ **Entrega:** <t:{ts}:D>  ·  <t:{ts}:R>")

    if s.payment_method == "cortesia":
        lines.append(f"🎁 **Regalo** (sin cobro)  ·  costo {_money(s.total_cost)}")
    else:
        lines.append(f"💰 **Precio:** {_money(s.price)}  ·  💳 {_esc(s.payment_method.capitalize(), 40)}")
    lines.append(f"🖨️ **Impresora:** {_esc(s.printer_name, 80)}")
    if s.warehouse_item_id is not None:
        lines.append("🏷️ **Pieza del Almacén** (ya fabricada)")
    elif s.filaments_used:
        filaments = "  ·  ".join(f"{_esc(f.filament_label, 60)} ({f.grams_used:.0f} g)" for f in s.filaments_used[:6])
        lines.append(f"🧵 **Filamento:** {filaments}")
    elif s.filament_label:
        lines.append(f"🧵 **Filamento:** {_esc(s.filament_label, 80)}")
    extra = [p for p in s.plates if not p.is_reprint]
    reprints = [p for p in s.plates if p.is_reprint]
    if extra:
        lines.append(f"🧩 **Planchas:** {1 + len(extra)}  ·  " + "  ·  ".join(_esc(p.name, 40) for p in extra[:5]))
    if reprints:
        lines.append(f"♻️ **Reimpresiones:** {len(reprints)}  ·  costo {_money(s.reprint_cost)}")
    if s.buyer_name:
        lines.append(f"👤 **Comprador:** {_esc(s.buyer_name, 80)}")
    if s.status == STATUS_CANCELLED and s.cancel_reason:
        lines.append(f"❌ **Motivo:** {_esc(s.cancel_reason, 300)}")
    if s.notes:
        lines.append(f"> 📝 {_esc(s.notes, 700)}")
    return "\n".join(lines)


def _progress(s: SaleResponse) -> str | None:
    if s.status not in dict(PROGRESS):
        return None
    current = [key for key, _ in PROGRESS].index(s.status)
    steps = []
    for i, (_, label) in enumerate(PROGRESS):
        if s.status == STATUS_DELIVERED or i < current:
            steps.append(f"✅ {label}")
        elif i == current:
            steps.append(f"🟢 **{label}**")
        else:
            steps.append(f"⬜ {label}")
    return "  ›  ".join(steps)


def _footer(s: SaleResponse) -> str:
    creator = _esc(s.created_by_username or "—", 40)
    owner = _esc(s.owner_username, 40)
    now = int(datetime.now(timezone.utc).timestamp())
    return f"-# Registrado por **{creator}**  ·  Inventario de **{owner}**  ·  Actualizado <t:{now}:R>"


def _v2_payload(s: SaleResponse) -> dict:
    header = {"type": TEXT, "content": _header(s)}
    logo = _logo()
    if logo:
        header = {
            "type": SECTION,
            "components": [header],
            "accessory": {"type": THUMBNAIL, "media": {"url": logo}, "description": "SS3D"},
        }
    parts = [
        header,
        {"type": SEPARATOR, "divider": True, "spacing": 1},
        {"type": TEXT, "content": _details(s)},
    ]
    progress = _progress(s)
    if progress:
        parts += [{"type": SEPARATOR, "divider": True, "spacing": 1}, {"type": TEXT, "content": progress}]
    parts.append({"type": TEXT, "content": _footer(s)})
    calendar = _calendar_url()
    if calendar and s.status != DELETED:
        parts.append({
            "type": ACTION_ROW,
            "components": [
                {"type": BUTTON, "style": LINK_BUTTON, "label": "Ver en el calendario", "emoji": {"name": "📅"},
                 "url": calendar},
            ],
        })
    return {
        "flags": IS_COMPONENTS_V2,
        "components": [{"type": CONTAINER, "accent_color": THEMES[s.status].color, "components": parts}],
        # Nunca notificar a nadie por un @ escrito en el nombre o las notas del pedido.
        "allowed_mentions": {"parse": []},
    }


def _embed_payload(s: SaleResponse) -> dict:
    theme = THEMES[s.status]
    description = f"{theme.badge}\n\n{_details(s)}"
    progress = _progress(s)
    if progress:
        description += f"\n\n{progress}"
    embed = {
        "author": {"name": f"{theme.kicker}  ·  #{s.id.hex[:6].upper()}"},
        "title": f"📦 {s.client_name}"[:256],
        "description": description[:4000],
        "color": theme.color,
        "footer": {"text": f"Registrado por {s.created_by_username or '—'} · Inventario de {s.owner_username}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logo = _logo()
    if logo:
        embed["author"]["icon_url"] = logo
        embed["thumbnail"] = {"url": logo}
    if _calendar_url() and s.status != DELETED:
        embed["url"] = _calendar_url()
    return {"embeds": [embed], "components": [], "allowed_mentions": {"parse": []}}
