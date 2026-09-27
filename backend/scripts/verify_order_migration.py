"""Verificación de cifras de la migración 0011 (estados de pedido). SOLO LECTURA.

Uso (desde la carpeta backend, con DATABASE_URL apuntando a la base a verificar):

    1) ANTES de migrar:   .\\venv\\Scripts\\python.exe scripts\\verify_order_migration.py snapshot antes.json
    2) Migrar:            .\\venv\\Scripts\\alembic.exe upgrade head
    3) DESPUÉS:           .\\venv\\Scripts\\python.exe scripts\\verify_order_migration.py compare antes.json

Qué compara: el Dashboard y el Historial cuentan ventas agrupadas por día. Antes de la
migración cuentan TODAS las ventas por su fecha de venta; después cuentan solo las
Entregadas por su fecha de entrega real. El script calcula, con cada regla, los totales
por dueño, quién registró, impresora, método de pago y día (trabajos, ingresos, ganancia,
costo, horas, gramos, depreciación, energía). Cualquier cifra del Dashboard, del
Historial o del contador de transferencias, de cualquier usuario y cualquier rango de
fechas, sale de sumar esas filas: si todas coinciden, todas las pantallas coinciden.
"""
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import settings  # noqa: E402

METRICS = ("jobs", "revenue", "profit", "cost", "hours", "grams", "depreciation", "energy")

BASE_SELECT = """
    SELECT s.user_id, s.created_by_user_id, s.printer_id, s.payment_method, {day} AS day,
           COUNT(*) AS jobs,
           COALESCE(SUM(s.base_price), 0) AS revenue,
           COALESCE(SUM(s.profit), 0) AS profit,
           COALESCE(SUM(s.total_cost), 0) AS cost,
           COALESCE(SUM(s.print_hours), 0) AS hours,
           COALESCE(SUM(s.grams_used), 0) AS grams,
           COALESCE(SUM(s.depreciation_cost), 0) AS depreciation,
           COALESCE(SUM(s.energy_cost), 0) AS energy
    FROM sales s
    {where}
    GROUP BY s.user_id, s.created_by_user_id, s.printer_id, s.payment_method, {day}
"""


def _has_status_column(conn) -> bool:
    return (
        conn.execute(
            text("SELECT 1 FROM information_schema.columns WHERE table_name = 'sales' AND column_name = 'status'")
        ).first()
        is not None
    )


def collect(conn) -> tuple[str, dict]:
    if _has_status_column(conn):
        mode = "despues (solo Entregadas, por fecha real)"
        sql = BASE_SELECT.format(day="s.delivered_date", where="WHERE s.status = 'entregada'")
    else:
        mode = "antes (todas las ventas, por fecha de venta)"
        sql = BASE_SELECT.format(day="s.sale_date", where="")
    rows = {}
    for r in conn.execute(text(sql)).mappings():
        key = "|".join(str(r[k]) for k in ("user_id", "created_by_user_id", "printer_id", "payment_method", "day"))
        rows[key] = {m: str(Decimal(r[m])) for m in METRICS}
    return mode, rows


def usernames(conn) -> dict:
    return {str(r[0]): r[1] for r in conn.execute(text("SELECT id, username FROM users"))}


def monthly_by_owner(rows: dict) -> dict:
    """Resumen legible: por dueño y mes (lo que muestra el Historial), + transferencias."""
    out = defaultdict(lambda: defaultdict(Decimal))
    for key, vals in rows.items():
        owner, _, _, payment, day = key.split("|")
        month = day[:7]
        for m in METRICS:
            out[(owner, month)][m] += Decimal(vals[m])
        if payment == "transferencia":
            out[(owner, month)]["transfers"] += Decimal(vals["jobs"])
    return out


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in ("snapshot", "compare"):
        print(__doc__)
        sys.exit(2)
    action, path = sys.argv[1], Path(sys.argv[2])
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        mode, rows = collect(conn)
        names = usernames(conn)
    print(f"Base: {engine.url.host} / {engine.url.database}  ·  regla: {mode}  ·  filas: {len(rows)}")

    if action == "snapshot":
        path.write_text(json.dumps({"mode": mode, "rows": rows}, indent=1), encoding="utf-8")
        print(f"Foto guardada en {path}. Ahora migra y luego corre: compare {path}")
        return

    before = json.loads(path.read_text(encoding="utf-8"))
    before_rows = before["rows"]
    if before["mode"] == mode:
        print("AVISO: la foto y la base usan la misma regla (¿se migró entre medio?).")

    diffs = []
    for key in sorted(set(before_rows) | set(rows)):
        a, b = before_rows.get(key), rows.get(key)
        if a is None or b is None or any(Decimal(a[m]) != Decimal(b[m]) for m in METRICS):
            diffs.append((key, a, b))

    ma, mb = monthly_by_owner(before_rows), monthly_by_owner(rows)
    print()
    print(f"{'Usuario':<16}{'Mes':<9}{'Trabajos':>9}{'Ingresos':>14}{'Ganancia':>14}{'Costo':>14}{'Transf.':>8}  Resultado")
    for owner, month in sorted(set(ma) | set(mb), key=lambda k: (names.get(k[0], k[0]), k[1])):
        a, b = ma.get((owner, month), {}), mb.get((owner, month), {})
        same = all(a.get(m, 0) == b.get(m, 0) for m in (*METRICS, "transfers"))
        print(
            f"{names.get(owner, owner)[:15]:<16}{month:<9}{int(b.get('jobs', 0)):>9}"
            f"{b.get('revenue', 0):>14,.0f}{b.get('profit', 0):>14,.0f}{b.get('cost', 0):>14,.0f}"
            f"{int(b.get('transfers', 0)):>8}  {'IGUAL' if same else 'DISTINTO'}"
        )
    print()
    if diffs:
        print(f"RESULTADO: {len(diffs)} diferencia(s). NO continuar; revisar:")
        for key, a, b in diffs[:20]:
            print(f"  {key}\n    antes:   {a}\n    despues: {b}")
        sys.exit(1)
    print(f"RESULTADO: OK. Las {len(rows)} filas (dueño × quién registró × impresora × pago × día) son idénticas.")


if __name__ == "__main__":
    main()
