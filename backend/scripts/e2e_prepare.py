"""Prepara la base DESECHABLE de los tests E2E (Playwright): la crea si falta, aplica las
migraciones y deja un usuario admin con contraseña conocida.

Igual que los tests de pytest, se niega a correr si DATABASE_URL no apunta a una base
LOCAL cuyo nombre termine en "_e2e": nunca toca datos reales.

    python scripts/e2e_prepare.py   (desde la carpeta backend, con DATABASE_URL definida)
"""
import os
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import psycopg  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

url = make_url(os.environ.get("DATABASE_URL", ""))
if not (url.database or "").endswith("_e2e") or url.host not in ("127.0.0.1", "localhost"):
    sys.exit(f"DATABASE_URL debe ser una base LOCAL terminada en '_e2e' (recibido: {url.host}/{url.database}).")

admin_dsn = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
with psycopg.connect(admin_dsn, autocommit=True) as conn:
    if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)).fetchone() is None:
        conn.execute(f'CREATE DATABASE "{url.database}"')

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

from app.database import SessionLocal  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import hash_password  # noqa: E402

USERNAME = os.environ.get("E2E_USERNAME", "e2e_admin")
PASSWORD = os.environ.get("E2E_PASSWORD", "e2e-password-123")

# La ventana de Novedades taparía la interfaz en cada test: se marca la última como vista.
notes = (BACKEND_DIR.parent / "frontend" / "src" / "releaseNotes.js").read_text(encoding="utf-8")
latest = re.search(r'id:\s*"([^"]+)"', notes)

with SessionLocal() as db:
    roles = {}
    for name in ("admin", "user", "watcher"):
        roles[name] = db.query(Role).filter(Role.name == name).first() or Role(name=name)
        db.add(roles[name])
    db.flush()
    user = db.query(User).filter(User.username == USERNAME).first()
    if user is None:
        user = User(username=USERNAME, password_hash="", role_id=roles["admin"].id)
        db.add(user)
    user.password_hash = hash_password(PASSWORD)
    user.is_active = True
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_seen_release = latest.group(1) if latest else None
    db.commit()

print(f"Base E2E lista ({url.database}), usuario {USERNAME}.")
