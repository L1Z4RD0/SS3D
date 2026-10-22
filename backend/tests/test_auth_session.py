"""Inicio y renovación de sesión: usuario sin distinguir mayúsculas y el minuto de margen
cuando la respuesta de /refresh no alcanza a llegar al navegador."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.security import hash_refresh_token

PASSWORD = "x" * 10  # la que pone Factory.user


@pytest.fixture
def browser():
    """Cliente propio por test: cada uno con su cookie de sesión, como un navegador nuevo."""
    return TestClient(app)


def _login(browser, username):
    r = browser.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return browser.cookies.get("refresh_token")


def _refresh_with(browser, raw):
    browser.cookies.clear()
    browser.cookies.set("refresh_token", raw, path="/api/auth")
    return browser.post("/api/auth/refresh")


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


def test_refresh_lost_response_keeps_session_for_a_minute(browser, make, db):
    user = make.user()
    first = _login(browser, user.username)
    r = _refresh_with(browser, first)
    assert r.status_code == 200
    # La respuesta "se perdió": el navegador vuelve a mandar la cookie anterior.
    r = _refresh_with(browser, first)
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]

    # Pasado el minuto, la cookie anterior ya no sirve.
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(first)).one()
    row.revoked_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    db.commit()
    assert _refresh_with(browser, first).status_code == 401


def test_logout_cookie_is_dead_immediately(browser, make):
    user = make.user()
    raw = _login(browser, user.username)
    assert browser.post("/api/auth/logout").status_code == 204
    assert _refresh_with(browser, raw).status_code == 401
