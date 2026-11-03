"""Volver de Entregada a Lista (corrección de una entrega marcada por error): el ingreso deja
de contar y vuelve a contar al entregarlo otra vez."""
from datetime import date
from decimal import Decimal

from conftest import deliver, sale_payload

TODAY = date.today()


def _summary(client, h):
    r = client.get("/api/dashboard/summary", headers=h, params={"date_from": str(TODAY), "date_to": str(TODAY)})
    assert r.status_code == 200, r.text
    return r.json()


def _status(client, h, sid, status):
    return client.post(f"/api/sales/{sid}/status", headers=h, json={"status": status, "today": str(TODAY)})


def test_undo_delivery_subtracts_and_redeliver_adds_back(client, make):
    u = make.user()
    h = make.headers(u)
    s = client.post("/api/sales", headers=h, json=sale_payload(make.printer(u), price=10000)).json()
    base = Decimal(_summary(client, h)["total_revenue"])
    deliver(client, h, s["id"], TODAY)
    assert Decimal(_summary(client, h)["total_revenue"]) == base + 10000

    r = _status(client, h, s["id"], "lista")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "lista" and r.json()["delivered_date"] is None
    assert "Corrección" in r.json()["status_history"][-1]["note"]
    assert Decimal(_summary(client, h)["total_revenue"]) == base

    assert _status(client, h, s["id"], "entregada").status_code == 200
    assert Decimal(_summary(client, h)["total_revenue"]) == base + 10000


def test_undo_delivery_of_warehouse_piece_reserves_it_again(client, make):
    u = make.user()
    h = make.headers(u)
    p, f = make.printer(u), make.filament(u)
    s = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100)).json()
    _status(client, h, s["id"], "en_produccion")
    piece = client.post(f"/api/sales/{s['id']}/cancel", headers=h,
                        json={"keep_hours": True, "piece_outcome": "almacen"}).json()["warehouse_piece"]
    sold = client.post(f"/api/warehouse/{piece['id']}/sell", headers=h,
                       json={"promised_delivery_date": str(TODAY), "payment_method": "efectivo"}).json()
    deliver(client, h, sold["id"], TODAY)
    items = {i["id"]: i for i in client.get("/api/warehouse", headers=h, params={"status": "todos"}).json()}
    assert items[piece["id"]]["status"] == "vendida"
    assert _status(client, h, sold["id"], "lista").status_code == 200
    items = {i["id"]: i for i in client.get("/api/warehouse", headers=h, params={"status": "todos"}).json()}
    assert items[piece["id"]]["status"] == "reservada"


def test_cancelled_still_final(client, make):
    u = make.user()
    h = make.headers(u)
    s = client.post("/api/sales", headers=h, json=sale_payload(make.printer(u))).json()
    client.post(f"/api/sales/{s['id']}/cancel", headers=h, json={})
    assert _status(client, h, s["id"], "lista").status_code == 409
