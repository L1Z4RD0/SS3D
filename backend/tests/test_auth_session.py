"""Inicio de sesión sin distinguir mayúsculas en el usuario (la renovación de sesión se
prueba en test_auth_refresh.py)."""
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.user import User

PASSWORD = "x" * 10  # la que pone Factory.user


@pytest.fixture
def browser():
    """Cliente propio por test: cada uno con su cookie de sesión, como un navegador nuevo."""
    return TestClient(app)


def _login(browser, username):
    r = browser.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return browser.cookies.get("refresh_token")


def test_login_ignores_username_case(browser, make):
    user = make.user(name="Diego")
    assert _login(browser, user.username.lower())
    assert _login(browser, user.username.upper())


def test_login_case_insensitive_is_ambiguous_when_two_users_differ_only_in_case(browser, make):
    user = make.user(name="Caso")
    twin = make.user(name="Twin")
    # Fuerza dos usuarios que solo se diferencian en mayúsculas.
    with SessionLocal() as db:
        db.get(User, twin.id).username = user.username.upper()
        db.commit()
    r = browser.post("/api/auth/login", json={"username": user.username.lower(), "password": PASSWORD})
    assert r.status_code == 401
    # El nombre exacto sigue entrando.
    assert _login(browser, user.username)


def test_wrong_password_still_rejected(browser, make):
    user = make.user()
    r = browser.post("/api/auth/login", json={"username": user.username.upper(), "password": "otra-clave-123"})
    assert r.status_code == 401
