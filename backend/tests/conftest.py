"""Configuración de los tests.

Los tests corren contra una base Postgres DESECHABLE (ver scripts/test_db.ps1) y borran
todo su contenido al empezar. Para que eso nunca pueda pasar con datos reales, se niegan
a correr si TEST_DATABASE_URL no apunta a una base local cuyo nombre termine en "_test".
"""
import os
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
if not TEST_DATABASE_URL:
    pytest.exit(
        "Falta TEST_DATABASE_URL. Levanta la base de pruebas con scripts/test_db.ps1 start y define "
        "TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5499/zola_test",
        returncode=2,
    )
_url = make_url(TEST_DATABASE_URL)
if not (_url.database or "").endswith("_test") or _url.host not in ("127.0.0.1", "localhost"):
    pytest.exit(
        f"TEST_DATABASE_URL debe ser una base LOCAL terminada en '_test' (recibido: {_url.host}/{_url.database}). "
        "Los tests borran la base: nunca se corren contra datos reales.",
        returncode=2,
    )

# La app lee la configuración al importarse: fijarla ANTES de importar nada de app.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "tests-only-secret-key")
os.chdir(BACKEND_DIR)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.filament import Filament  # noqa: E402
from app.models.printer import Printer  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.supply import Supply  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.watcher_assignment import WatcherAssignment  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _fresh_schema():
    """Base vacía + todas las migraciones, igual que en producción."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    with SessionLocal() as db:
        for name in ("admin", "user", "watcher"):
            if db.query(Role).filter(Role.name == name).first() is None:
                db.add(Role(id=uuid.uuid4(), name=name))
        db.commit()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


class Factory:
    """Crea datos de prueba con nombres únicos, para que los tests no choquen entre sí."""

    def __init__(self, db):
        self.db = db

    def user(self, role="user", name="user"):
        role_row = self.db.query(Role).filter(Role.name == role).one()
        u = User(username=f"{name}_{uuid.uuid4().hex[:8]}", password_hash=hash_password("x" * 10), role_id=role_row.id)
        self.db.add(u)
        self.db.commit()
        return u

    def assign(self, watcher, owner):
        self.db.add(WatcherAssignment(watcher_user_id=watcher.id, observed_user_id=owner.id))
        self.db.commit()

    def printer(self, owner, **kw):
        p = Printer(user_id=owner.id, name=kw.get("name", "Impresora"), purchase_value=Decimal(300000),
                    lifetime_hours=Decimal(2000), power_kw=Decimal("0.2"), hours_used=Decimal(0),
                    depreciation_cost_per_hour=Decimal(150))
        self.db.add(p)
        self.db.commit()
        return p

    def filament(self, owner, grams=1000, **kw):
        f = Filament(user_id=owner.id, brand=kw.get("brand", "Esun"), type="PLA", color=kw.get("color", "Rojo"),
                     entry_date=date.today(), spool_weight_g=Decimal(1000), initial_stock_g=Decimal(grams),
                     used_g=Decimal(0), available_g=Decimal(grams), min_alert_g=Decimal(100), spool_price=Decimal(10000))
        self.db.add(f)
        self.db.commit()
        return f

    def supply(self, owner, qty=50, unit_cost=100):
        s = Supply(user_id=owner.id, name="Argolla", category="Argollas", quantity_available=Decimal(qty),
                   unit_cost=Decimal(unit_cost))
        self.db.add(s)
        self.db.commit()
        return s

    def headers(self, user):
        role = self.db.get(Role, user.role_id).name
        return {"Authorization": f"Bearer {create_access_token(user.id, role)}"}


@pytest.fixture
def make(db):
    return Factory(db)


def deliver(client, headers, sale_id, today=None):
    """Marca un pedido como Entregado (saltando pasos, con la confirmación)."""
    body = {"status": "entregada", "skip_confirmed": True}
    if today is not None:
        body["today"] = str(today)
    r = client.post(f"/api/sales/{sale_id}/status", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def sale_payload(printer, filament=None, grams=100, supply=None, qty=2, price=9000, **extra):
    body = {
        "sale_date": str(date.today()),
        "client_name": "Llavero",
        "printer_id": str(printer.id),
        "filaments": [{"filament_id": str(filament.id), "grams_used": grams}] if filament else [],
        "print_hours": 2,
        "postprocess_hours": 0.5,
        "shipping_cost": 3000,
        "supplies": [{"supply_id": str(supply.id), "quantity": qty}] if supply else [],
        "price": price,
        "payment_method": "efectivo",
    }
    body.update({k: str(v) if isinstance(v, uuid.UUID) else v for k, v in extra.items()})
    return body
