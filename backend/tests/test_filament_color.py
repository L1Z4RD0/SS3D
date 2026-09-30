"""Color exacto (RGB) de los filamentos."""
from datetime import date


def _body(**extra):
    body = {"brand": "Sunlu", "type": "PLA", "color": "Verde agua", "entry_date": str(date.today()),
            "initial_stock_g": 1000, "min_alert_g": 100, "spool_price": 15000}
    body.update(extra)
    return body


def test_filament_saves_exact_color(client, make):
    u = make.user()
    h = make.headers(u)
    r = client.post("/api/inventory/filaments", headers=h, json=_body(color_hex="#1ABC9C"))
    assert r.status_code == 201, r.text
    assert r.json()["color_hex"] == "#1abc9c"  # se guarda normalizado en minúsculas

    f_id = r.json()["id"]
    r = client.put(f"/api/inventory/filaments/{f_id}", headers=h, json={"color_hex": "#FF8800"})
    assert r.json()["color_hex"] == "#ff8800"
    # Se puede volver al color del catálogo.
    r = client.put(f"/api/inventory/filaments/{f_id}", headers=h, json={"color_hex": None})
    assert r.json()["color_hex"] is None


def test_filament_without_exact_color_keeps_working(client, make):
    """Los filamentos anteriores (sin color_hex) siguen igual: el campo viene vacío."""
    u = make.user()
    f = make.filament(u)
    listed = client.get("/api/inventory/filaments", headers=make.headers(u)).json()
    assert [x["color_hex"] for x in listed if x["id"] == str(f.id)] == [None]
    r = client.post("/api/inventory/filaments", headers=make.headers(u), json=_body())
    assert r.status_code == 201 and r.json()["color_hex"] is None


def test_filament_rejects_invalid_color(client, make):
    h = make.headers(make.user())
    for bad in ("rojo", "#12345", "#GGGGGG", "123456", "#1234567"):
        r = client.post("/api/inventory/filaments", headers=h, json=_body(color_hex=bad))
        assert r.status_code == 422, bad
