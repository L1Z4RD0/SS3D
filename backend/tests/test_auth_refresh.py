"""Rotación del refresh token: dos refresh casi simultáneos con la misma cookie no deben
sacar al usuario de la sesión, pero un token de una sesión cerrada sigue sin valer."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.refresh_token import RefreshToken
from app.routers.auth import REFRESH_COOKIE_NAME, ROTATION_GRACE
from app.security import hash_refresh_token


def _login(make):
    user = make.user()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user.username, "password": "x" * 10})
    assert r.status_code == 200
    return c, r.cookies[REFRESH_COOKIE_NAME]


def _refresh_with(cookie):
    return TestClient(app).post("/api/auth/refresh", cookies={REFRESH_COOKIE_NAME: cookie})


def test_recently_rotated_token_is_accepted(make):
    _, cookie = _login(make)
    assert _refresh_with(cookie).status_code == 200
    # Segunda pestaña que salió con la misma cookie un instante después.
    r = _refresh_with(cookie)
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_rotated_token_expires_after_grace(make, db):
    _, cookie = _login(make)
    assert _refresh_with(cookie).status_code == 200
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(cookie)).one()
    row.revoked_at = datetime.now(timezone.utc) - ROTATION_GRACE - timedelta(seconds=1)
    db.commit()
    assert _refresh_with(cookie).status_code == 401


def test_logged_out_token_is_rejected_immediately(make):
    c, cookie = _login(make)
    assert c.post("/api/auth/logout").status_code == 204
    assert _refresh_with(cookie).status_code == 401


def test_logout_also_kills_recently_rotated_tokens(make):
    c, old_cookie = _login(make)
    new_cookie = _refresh_with(old_cookie).cookies[REFRESH_COOKIE_NAME]
    logout = TestClient(app).post("/api/auth/logout", cookies={REFRESH_COOKIE_NAME: new_cookie})
    assert logout.status_code == 204
    # El token anterior seguía en la ventana de gracia: tras el logout ya no sirve.
    assert _refresh_with(old_cookie).status_code == 401
