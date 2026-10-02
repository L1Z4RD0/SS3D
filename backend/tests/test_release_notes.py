"""Ventana de Novedades: se marca como vista por usuario."""


def test_release_seen_is_saved_per_user(client, make):
    a, b = make.user(), make.user()
    assert client.get("/api/auth/me", headers=make.headers(a)).json()["last_seen_release"] is None
    r = client.post("/api/auth/me/release-seen", headers=make.headers(a), json={"release": "2026-10-02"})
    assert r.status_code == 204
    assert client.get("/api/auth/me", headers=make.headers(a)).json()["last_seen_release"] == "2026-10-02"
    # Otro usuario no se ve afectado.
    assert client.get("/api/auth/me", headers=make.headers(b)).json()["last_seen_release"] is None
    # Una versión más nueva reemplaza a la anterior (no se acumulan).
    client.post("/api/auth/me/release-seen", headers=make.headers(a), json={"release": "2026-11-15"})
    assert client.get("/api/auth/me", headers=make.headers(a)).json()["last_seen_release"] == "2026-11-15"


def test_release_seen_validation(client, make):
    h = make.headers(make.user())
    assert client.post("/api/auth/me/release-seen", headers=h, json={"release": ""}).status_code == 422
    assert client.post("/api/auth/me/release-seen", json={"release": "x"}).status_code == 401
