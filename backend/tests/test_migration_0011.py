"""Migración 0011: las ventas existentes pasan a Entregada sin que cambie ninguna cifra.

Usa una SEGUNDA base desechable (<base de tests>_mig_test): la deja en la versión 0010,
carga ventas de dos usuarios y un observador en varios meses (con transferencias y una
venta antigua con IVA), toma la foto de cifras con el script de verificación, migra,
compara y prueba que la migración se puede revertir.
"""
import os
import random
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
PY = sys.executable


def _run(args, url):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run([PY, *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=300)


@pytest.fixture(scope="module")
def mig_url():
    base = make_url(os.environ["TEST_DATABASE_URL"])
    name = f"{base.database[:-5]}_mig_test"  # zola_test -> zola_mig_test
    url = base.set(database=name)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    yield url.render_as_string(hide_password=False)
    admin.dispose()


def _seed_at_0010(url):
    """Datos realistas en el esquema 0010 (antes de los estados de pedido)."""
    rng = random.Random(42)
    eng = create_engine(url)
    today = date.today()
    with eng.begin() as c:
        roles = {}
        for name in ("admin", "user", "watcher"):
            rid = c.execute(text("SELECT id FROM roles WHERE name = :n"), {"n": name}).scalar()
            if rid is None:
                rid = uuid.uuid4()
                c.execute(text("INSERT INTO roles (id, name) VALUES (:i, :n)"), {"i": rid, "n": name})
            roles[name] = rid
        users = {}
        for uname, role in (("sntg", "user"), ("ana", "user"), ("olzer", "watcher")):
            uid = uuid.uuid4()
            c.execute(text("INSERT INTO users (id, username, password_hash, role_id) VALUES (:i, :u, 'x', :r)"),
                      {"i": uid, "u": uname, "r": roles[role]})
            users[uname] = uid
        printers = {}
        for owner in ("sntg", "ana"):
            for n in (1, 2):
                pid = uuid.uuid4()
                c.execute(text(
                    "INSERT INTO printers (id, user_id, name, purchase_value, lifetime_hours, power_kw, "
                    "depreciation_cost_per_hour) VALUES (:i, :u, :n, 300000, 2000, 0.2, 150)"),
                    {"i": pid, "u": users[owner], "n": f"P{n}-{owner}"})
                printers.setdefault(owner, []).append(pid)
        count = 0
        for owner in ("sntg", "ana"):
            for i in range(60):
                day = today - timedelta(days=rng.randint(0, 150))
                base = rng.randint(3000, 40000)
                iva_old = i % 17 == 0  # algunas ventas antiguas con IVA
                iva = round(base * 0.19, 2) if iva_old else 0
                cost = round(base * rng.uniform(0.3, 0.8), 2)
                creator = users["olzer"] if (owner == "sntg" and i % 5 == 0) else users[owner]
                c.execute(text(
                    "INSERT INTO sales (id, user_id, created_by_user_id, sale_date, client_name, printer_id, "
                    "grams_used, print_hours, postprocess_hours, base_price, iva_percent, iva_amount, total_price, "
                    "material_cost, depreciation_cost, energy_cost, postprocess_cost, supplies_cost, shipping_cost, "
                    "total_cost, profit, margin_percent, payment_method, created_at) VALUES "
                    "(:id, :u, :cb, :d, 'Trabajo', :p, :g, :h, 0, :b, :ivp, :iva, :t, :mat, :dep, :en, 0, 0, 0, "
                    ":cost, :profit, 10, :pm, :ca)"),
                    {"id": uuid.uuid4(), "u": users[owner], "cb": creator, "d": day,
                     "p": rng.choice(printers[owner]), "g": rng.randint(5, 400), "h": rng.randint(1, 12),
                     "b": base, "ivp": 19 if iva_old else 0, "iva": iva, "t": base + iva,
                     "mat": round(cost * 0.5, 2), "dep": round(cost * 0.3, 2), "en": round(cost * 0.2, 2),
                     "cost": cost, "profit": round(base - cost, 2),
                     "pm": rng.choice(["efectivo", "transferencia", "transferencia", "debito", "por_cobrar", "cortesia"]),
                     "ca": datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=15)})
                count += 1
    eng.dispose()
    return count


def test_migration_keeps_every_figure_identical(mig_url, tmp_path):
    r = _run(["-m", "alembic", "upgrade", "0010_sale_created_by"], mig_url)
    assert r.returncode == 0, r.stderr
    total = _seed_at_0010(mig_url)

    snap = tmp_path / "antes.json"
    r = _run(["scripts/verify_order_migration.py", "snapshot", str(snap)], mig_url)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "antes" in r.stdout

    r = _run(["-m", "alembic", "upgrade", "head"], mig_url)
    assert r.returncode == 0, r.stderr

    r = _run(["scripts/verify_order_migration.py", "compare", str(snap)], mig_url)
    print(r.stdout)  # visible con pytest -s: tabla por usuario y mes
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RESULTADO: OK" in r.stdout

    eng = create_engine(mig_url)
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM sales WHERE status = 'entregada' "
                              "AND promised_delivery_date = sale_date AND delivered_date = sale_date")).scalar() == total
        assert c.execute(text("SELECT count(*) FROM sale_status_history WHERE is_migration")).scalar() == total
        # Montos intactos (incluidas las ventas antiguas con IVA)
        assert c.execute(text("SELECT count(*) FROM sales WHERE iva_amount > 0 AND total_price = base_price + iva_amount")).scalar() > 0
    eng.dispose()


def test_migration_can_be_reverted_and_reapplied(mig_url):
    r = _run(["-m", "alembic", "downgrade", "0010_sale_created_by"], mig_url)
    assert r.returncode == 0, r.stderr
    eng = create_engine(mig_url)
    with eng.connect() as c:
        cols = {row[0] for row in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'sales'"))}
        assert "status" not in cols
        assert c.execute(text("SELECT count(*) FROM sales")).scalar() > 0  # las ventas siguen ahí
    eng.dispose()
    r = _run(["-m", "alembic", "upgrade", "head"], mig_url)
    assert r.returncode == 0, r.stderr
