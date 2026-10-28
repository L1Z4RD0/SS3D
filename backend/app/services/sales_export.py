"""Excel de la hoja de Ventas: las mismas ventas, filtros y orden que se ven en pantalla
(todas las páginas). Tres hojas:

- Ventas: una fila por pedido, con el costo desglosado y una fila de totales.
- Costos por cuenta: de quién es cada costo (máquina, material, insumos), según el dueño de
  cada recurso usado. La cuenta que registra la venta no carga con costos que no son suyos.
- Resumen: pedidos e importes por estado, por fuente de venta y costos por cuenta.
"""
from collections import defaultdict
from decimal import Decimal

from app.constants import NO_SALE_SOURCE
from app.schemas.sale import SaleResponse
from app.services import xlsx
from app.services.xlsx import Col

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
SOURCE_LABELS = {"instagram": "Instagram", "facebook": "Facebook", "personal": "Personal", NO_SALE_SOURCE: "Sin registrar"}

SALE_COLS = [
    Col("N°", 6),
    Col("Fecha del pedido", 12, "date"),
    Col("Entrega comprometida", 12, "date"),
    Col("Entrega real", 12, "date"),
    Col("Estado", 13),
    Col("Trabajo", 28),
    Col("Comprador", 18),
    Col("Cuenta dueña (inventario)", 20),
    Col("Registrada por", 20),
    Col("Fuente de venta", 13),
    Col("Método de pago", 14),
    Col("Impresora", 16),
    Col("Horas de impresión", 10, "hours"),
    Col("Horas de postprocesado", 12, "hours"),
    Col("Filamentos usados", 32),
    Col("Insumos usados", 26),
    Col("Precio cobrado", 13, "money"),
    Col("Material", 12, "money"),
    Col("Depreciación", 12, "money"),
    Col("Luz", 10, "money"),
    Col("Insumos ($)", 11, "money"),
    Col("Postprocesado", 13, "money"),
    Col("Delivery", 11, "money"),
    Col("Costo total", 13, "money"),
    Col("Ganancia", 13, "money"),
    Col("Margen", 9, "percent"),
    Col("Reserva por riesgo (incluida en la ganancia)", 14, "money"),
    Col("Pérdida (si se canceló)", 12, "money"),
    Col("Delivery lo llevó", 14),
    Col("Notas", 40),
]
# Columnas de montos que suman en la fila de total (índices en SALE_COLS).
SALE_TOTALS = {i: "sum" for i, c in enumerate(SALE_COLS) if c.kind == "money"}

OWNER_COLS = [
    Col("Fecha del pedido", 12, "date"),
    Col("Trabajo", 28),
    Col("Estado", 13),
    Col("Registrada por", 20),
    Col("Cuenta que puso el recurso", 20),
    Col("Máquina (depreciación + luz)", 16, "money"),
    Col("Material (filamento)", 14, "money"),
    Col("Insumos", 12, "money"),
    Col("Total de esa cuenta", 14, "money"),
]


def _materials(s: SaleResponse) -> str:
    if s.filaments_used:
        return ", ".join(f"{f.filament_label} ({f.grams_used:.0f} g)" for f in s.filaments_used)
    if s.filament_label:
        return f"{s.filament_label} ({s.grams_used:.0f} g)"
    return "Pieza del Almacén" if s.warehouse_item_id else ""


def _supplies(s: SaleResponse) -> str:
    return ", ".join(f"{u.supply_name} x{u.quantity_used:g}" for u in s.supplies_used)


def _sale_row(n: int, s: SaleResponse) -> list:
    cancelled = s.status == "cancelado"
    return [
        n, s.sale_date, s.promised_delivery_date, s.delivered_date, STATUS_LABELS.get(s.status, s.status),
        s.client_name, s.buyer_name or "", s.owner_username, s.created_by_username or "",
        SOURCE_LABELS.get(s.sale_source or NO_SALE_SOURCE), PAYMENT_LABELS.get(s.payment_method, s.payment_method),
        s.printer_name, s.print_hours, s.postprocess_hours, _materials(s), _supplies(s),
        s.price, s.material_cost, s.depreciation_cost, s.energy_cost, s.supplies_cost, s.postprocess_cost,
        s.shipping_cost, s.total_cost,
        None if cancelled else s.profit,
        None if cancelled else Decimal(s.margin_percent) / 100,
        s.risk_amount, s.loss_amount if cancelled else None, s.delivery_by or "", s.notes or "",
    ]


def build_sales_workbook(sales: list[SaleResponse], filters_text: str) -> bytes:
    wb = xlsx.new_workbook()

    # ---- Ventas ----
    ws = xlsx.sheet(wb, "Ventas")
    row = xlsx.title(ws, "Zola · Ventas", f"Descargado el {xlsx.today_label()} · {len(sales)} pedido(s) · {filters_text}")
    row = xlsx.note(ws, row, (
        "Costo total = Material + Depreciación + Luz + Insumos + Postprocesado + Delivery. "
        "Ganancia = Precio cobrado − Costo total (la reserva por riesgo de fallo ya está dentro de la ganancia). "
        "Margen = Ganancia ÷ Precio cobrado. En los cancelados no hay ganancia: se muestra la pérdida."
    ), span=12)
    row = xlsx.table(ws, row + 1, SALE_COLS, [_sale_row(i, s) for i, s in enumerate(sales, start=1)],
                     totals=SALE_TOTALS, freeze=True)

    # ---- Costos por cuenta ----
    ws = xlsx.sheet(wb, "Costos por cuenta")
    row = xlsx.title(ws, "Costos por cuenta", "De quién es cada costo de cada pedido")
    row = xlsx.note(ws, row, (
        "Cada costo es de quien puso el recurso: la máquina (depreciación + luz) es del dueño de la impresora; el "
        "material, del dueño de cada filamento; los insumos, del dueño de cada insumo. La cuenta que registra la "
        "venta no carga con costos que no son suyos. El postprocesado no es de nadie (ganancia común) y el delivery "
        "es de quien lo llevó, por eso no aparecen aquí."
    ), span=9)
    owner_rows = []
    for s in sales:
        for oc in s.cost_by_owner:
            owner_rows.append([s.sale_date, s.client_name, STATUS_LABELS.get(s.status, s.status),
                               s.created_by_username or "", oc.username, oc.machine, oc.material, oc.supplies, oc.total])
    xlsx.table(ws, row + 1, OWNER_COLS, owner_rows, totals={5: "sum", 6: "sum", 7: "sum", 8: "sum"}, freeze=True)

    # ---- Resumen ----
    ws = xlsx.sheet(wb, "Resumen")
    row = xlsx.title(ws, "Resumen", filters_text)
    summary_cols = [Col("", 22), Col("Pedidos", 10), Col("Precio cobrado", 15, "money"),
                    Col("Costo total", 15, "money"), Col("Ganancia", 15, "money")]

    def grouped(key) -> list[list]:
        acc: dict[str, list] = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0)])
        for s in sales:
            a = acc[key(s)]
            a[0] += 1
            a[1] += s.price
            a[2] += s.total_cost
            a[3] += Decimal(0) if s.status == "cancelado" else s.profit
        return [[k, *v] for k, v in acc.items()]

    row = xlsx.section(ws, row, "Por estado")
    summary_cols[0] = Col("Estado", 22)
    row = xlsx.table(ws, row, list(summary_cols), grouped(lambda s: STATUS_LABELS.get(s.status, s.status)),
                     totals={1: "sum", 2: "sum", 3: "sum", 4: "sum"})
    row = xlsx.section(ws, row, "Por fuente de venta")
    summary_cols[0] = Col("Fuente", 22)
    row = xlsx.table(ws, row, list(summary_cols), grouped(lambda s: SOURCE_LABELS.get(s.sale_source or NO_SALE_SOURCE)),
                     totals={1: "sum", 2: "sum", 3: "sum", 4: "sum"})

    per_owner: dict[str, list] = defaultdict(lambda: [Decimal(0)] * 4)
    for s in sales:
        for oc in s.cost_by_owner:
            p = per_owner[oc.username]
            p[0] += oc.machine
            p[1] += oc.material
            p[2] += oc.supplies
            p[3] += oc.total
    row = xlsx.section(ws, row, "Costos por cuenta (quién puso cada recurso)")
    xlsx.table(ws, row, [Col("Cuenta", 22), Col("Máquina", 15, "money"), Col("Material", 15, "money"),
                         Col("Insumos", 15, "money"), Col("Total", 15, "money")],
               [[k, *v] for k, v in sorted(per_owner.items())], totals={1: "sum", 2: "sum", 3: "sum", 4: "sum"})

    return xlsx.to_bytes(wb)
