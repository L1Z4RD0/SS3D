"""Fase 5: acciones del Almacén, reglas del Observador y tarjetas nuevas del Dashboard."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from conftest import deliver, sale_payload

from app.models.audit_log import AuditLog
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.warehouse_item import WarehouseItem

TODAY = date.today()


def _piece_for(client, h, printer, filament, price=9000):
    """Pedido de 100 g y 2 h, cancelado En producción con la pieza al Almacén."""
    s = client.post("/api/sales", headers=h, json=sale_payload(printer, filament, 100, price=price)).json()
    client.post(f"/api/sales/{s['id']}/status", headers=h, json={"status": "en_produccion"})
    r = client.post(f"/api/sales/{s['id']}/cancel", headers=h, json={"keep_hours": True, "piece_outcome": "almacen"})
    assert r.status_code == 200, r.text
    return r.json()["warehouse_piece"], s


@pytest.fixture
def owner(client, make):
    u = make.user(name="sntg")
    p, f = make.printer(u), make.filament(u)
    h = make.headers(u)
    piece, origin = _piece_for(client, h, p, f)
    return {"u": u, "h": h, "p": p, "f": f, "piece": piece, "origin": origin}


def _list(client, h, **params):
    r = client.get("/api/warehouse", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _sell(client, h, piece_id, **kw):
    body = {"promised_delivery_date": str(TODAY + timedelta(days=2)), "payment_method": "efectivo", **kw}
    return client.post(f"/api/warehouse/{piece_id}/sell", headers=h, json=body)


# ---------------- Listado ----------------

def test_list_defaults_to_in_stock_and_reserved(client, owner):
    items = _list(client, owner["h"])
    assert [i["id"] for i in items] == [owner["piece"]["id"]]
    it = items[0]
    assert it["status"] == "en_almacen" and it["can_manage"] is True
    assert it["origin_client_name"] == "Llavero" and it["owner_username"] == owner["u"].username


def test_other_users_do_not_see_my_warehouse(client, make, owner):
    other = make.user()
    assert _list(client, make.headers(other), status="todos") == []
    assert client.post(f"/api/warehouse/{owner['piece']['id']}/sell", headers=make.headers(other),
                       json={"promised_delivery_date": str(TODAY), "payment_method": "efectivo"}).status_code == 404


# ---------------- Vender ----------------

def test_sell_creates_ready_order_without_consuming(client, db, owner):
    db.expire_all()
    grams_before = db.get(Filament, owner["f"].id).available_g
    hours_before = db.get(Printer, owner["p"].id).hours_used
    r = _sell(client, owner["h"], owner["piece"]["id"], buyer_name="María", price=8000)
    assert r.status_code == 201, r.text
    sale = r.json()
    assert sale["status"] == "lista" and sale["warehouse_item_id"] == owner["piece"]["id"]
    assert sale["client_name"] == "Llavero" and sale["buyer_name"] == "María"
    assert Decimal(sale["total_cost"]) == Decimal(owner["piece"]["cost"])
    assert Decimal(sale["profit"]) == Decimal(8000) - Decimal(owner["piece"]["cost"])
    assert Decimal(sale["grams_used"]) == 0 and Decimal(sale["print_hours"]) == 0
    db.expire_all()
    assert db.get(Filament, owner["f"].id).available_g == grams_before
    assert db.get(Printer, owner["p"].id).hours_used == hours_before
    item = db.get(WarehouseItem, owner["piece"]["id"])
    assert item.status == "reservada"
    listed = _list(client, owner["h"])[0]
    assert listed["status"] == "reservada" and listed["active_sale_id"] == sale["id"]


def test_sell_uses_piece_price_by_default_and_cannot_resell(client, owner):
    r = _sell(client, owner["h"], owner["piece"]["id"])
    assert Decimal(r.json()["price"]) == Decimal(owner["piece"]["price"])
    assert _sell(client, owner["h"], owner["piece"]["id"]).status_code == 409  # ya reservada


def test_delivering_marks_piece_sold_and_counts_income_with_piece_cost(client, db, owner):
    sale = _sell(client, owner["h"], owner["piece"]["id"], price=10000).json()
    # Nace Lista: no puede volver a producción
    r = client.post(f"/api/sales/{sale['id']}/status", headers=owner["h"], json={"status": "en_produccion"})
    assert r.status_code == 400
    deliver(client, owner["h"], sale["id"], TODAY)
    db.expire_all()
    assert db.get(WarehouseItem, owner["piece"]["id"]).status == "vendida"
    s = client.get("/api/dashboard/summary", headers=owner["h"],
                   params={"date_from": str(TODAY), "date_to": str(TODAY)}).json()
    assert s["total_jobs"] == 1 and Decimal(s["total_revenue"]) == 10000
    assert Decimal(s["total_cost"]) == Decimal(owner["piece"]["cost"])
    assert Decimal(s["warehouse_value"]) == 0  # vendida: ya no es valor en Almacén


def test_cancelling_warehouse_order_returns_piece(client, db, owner):
    sale = _sell(client, owner["h"], owner["piece"]["id"]).json()
    r = client.post(f"/api/sales/{sale['id']}/cancel", headers=owner["h"], json={})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["loss_amount"]) == 0
    db.expire_all()
    assert db.get(WarehouseItem, owner["piece"]["id"]).status == "en_almacen"
    assert _sell(client, owner["h"], owner["piece"]["id"]).status_code == 201  # se puede volver a vender


def test_deleting_warehouse_order_returns_piece_without_touching_stock(client, db, owner):
    sale = _sell(client, owner["h"], owner["piece"]["id"]).json()
    db.expire_all()
    grams = db.get(Filament, owner["f"].id).available_g
    assert client.delete(f"/api/sales/{sale['id']}", headers=owner["h"]).status_code == 204
    db.expire_all()
    assert db.get(WarehouseItem, owner["piece"]["id"]).status == "en_almacen"
    assert db.get(Filament, owner["f"].id).available_g == grams


def test_warehouse_order_never_edits_materials(client, owner):
    sale = _sell(client, owner["h"], owner["piece"]["id"]).json()
    r = client.put(f"/api/sales/{sale['id']}", headers=owner["h"], json={"print_hours": 3})
    assert r.status_code == 409
    deliver(client, owner["h"], sale["id"])
    r = client.put(f"/api/sales/{sale['id']}", headers=owner["h"],
                   json={"filaments": [{"filament_id": str(owner["f"].id), "grams_used": 10}]})
    assert r.status_code == 409  # tampoco una vez entregado
    r = client.put(f"/api/sales/{sale['id']}", headers=owner["h"],
                   json={"price": 7000, "delivered_date": str(TODAY - timedelta(days=1))})
    assert r.status_code == 200 and r.json()["delivered_date"] == str(TODAY - timedelta(days=1))


# ---------------- Editar y descartar ----------------

def test_edit_piece(client, db, owner):
    r = client.patch(f"/api/warehouse/{owner['piece']['id']}", headers=owner["h"],
                     json={"name": "Llavero rojo", "price": 500, "notes": "rayita"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["name"], Decimal(d["price"]), d["notes"]) == ("Llavero rojo", Decimal(500), "rayita")
    assert db.query(AuditLog).filter(AuditLog.entity_id == d["id"],
                                     AuditLog.event_type == "WAREHOUSE_ITEM_UPDATED").count() == 1


def test_discard_piece_counts_as_loss(client, db, owner):
    cost = Decimal(owner["piece"]["cost"])
    before = client.get("/api/dashboard/summary", headers=owner["h"]).json()
    assert Decimal(before["warehouse_value"]) == cost and Decimal(before["total_losses"]) == 0
    assert client.post(f"/api/warehouse/{owner['piece']['id']}/discard", headers=owner["h"],
                       json={"reason": "raro"}).status_code == 422
    r = client.post(f"/api/warehouse/{owner['piece']['id']}/discard", headers=owner["h"],
                    json={"reason": "regalada", "note": "para la vecina"})
    assert r.status_code == 200 and r.json()["status"] == "descartada"
    after = client.get("/api/dashboard/summary", headers=owner["h"]).json()
    assert Decimal(after["warehouse_value"]) == 0 and Decimal(after["total_losses"]) == cost
    # Fuera del período, la pérdida no aparece
    past = client.get("/api/dashboard/summary", headers=owner["h"],
                      params={"date_from": "2020-01-01", "date_to": "2020-01-31"}).json()
    assert Decimal(past["total_losses"]) == 0
    assert _list(client, owner["h"]) == []  # por defecto no se listan descartadas
    assert [i["status"] for i in _list(client, owner["h"], status="descartada")] == ["descartada"]


def test_reserved_piece_cannot_be_discarded(client, owner):
    _sell(client, owner["h"], owner["piece"]["id"])
    r = client.post(f"/api/warehouse/{owner['piece']['id']}/discard", headers=owner["h"], json={"reason": "danada"})
    assert r.status_code == 409


# ---------------- Observador ----------------

def test_watcher_sees_by_owner_can_sell_but_not_manage(client, make, owner):
    stranger = make.user(name="ana")
    sp, sf = make.printer(stranger), make.filament(stranger)
    _piece_for(client, make.headers(stranger), sp, sf)
    w = make.user("watcher", "olzer")
    make.assign(w, owner["u"])
    wh = make.headers(w)

    items = _list(client, wh)
    assert [i["id"] for i in items] == [owner["piece"]["id"]]  # nada del no asignado
    assert items[0]["can_manage"] is False and items[0]["owner_id"] == str(owner["u"].id)
    assert client.patch(f"/api/warehouse/{owner['piece']['id']}", headers=wh, json={"price": 1}).status_code == 403
    assert client.post(f"/api/warehouse/{owner['piece']['id']}/discard", headers=wh,
                       json={"reason": "danada"}).status_code == 403

    r = _sell(client, wh, owner["piece"]["id"])
    assert r.status_code == 201, r.text
    sale = r.json()
    assert sale["owner_username"] == owner["u"].username and sale["created_by_username"] == w.username
    # El dueño lo ve registrado por el observador y puede gestionarlo
    mine = {x["id"]: x for x in client.get("/api/sales", headers=owner["h"]).json()["items"]}
    assert mine[sale["id"]]["created_by_username"] == w.username and mine[sale["id"]]["can_edit"] is True


def test_watcher_loses_access_when_unassigned(client, db, make, owner):
    w = make.user("watcher", "olzer")
    make.assign(w, owner["u"])
    from app.models.watcher_assignment import WatcherAssignment

    db.query(WatcherAssignment).filter(WatcherAssignment.watcher_user_id == w.id).delete()
    db.commit()
    assert _list(client, make.headers(w)) == []
    assert _sell(client, make.headers(w), owner["piece"]["id"]).status_code == 404


# ---------------- Tarjetas del Dashboard ----------------

def test_dashboard_open_orders_losses_and_warehouse_value(client, make):
    u = make.user()
    h = make.headers(u)
    p, f = make.printer(u), make.filament(u)
    a = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100)).json()   # abierto
    b = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100)).json()
    client.post(f"/api/sales/{b['id']}/status", headers=h, json={"status": "en_produccion"})  # abierto
    c = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100)).json()
    deliver(client, h, c["id"])                                                      # no abierto
    d = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100)).json()
    client.post(f"/api/sales/{d['id']}/status", headers=h, json={"status": "en_produccion"})
    lost = client.post(f"/api/sales/{d['id']}/cancel", headers=h,
                       json={"keep_hours": False, "piece_outcome": "inutilizable"}).json()
    piece, _ = _piece_for(client, h, p, f)

    s = client.get("/api/dashboard/summary", headers=h,
                   params={"date_from": str(TODAY), "date_to": str(TODAY)}).json()
    assert s["open_orders"] == 2
    assert Decimal(s["total_losses"]) == Decimal(lost["loss_amount"]) > 0
    assert Decimal(s["warehouse_value"]) == Decimal(piece["cost"])
    assert a["id"]  # (usado)


def test_resources_of_pieces_count_as_history(client, db, owner):
    """La impresora y el filamento de una pieza del Almacén no se borran: se desactivan."""
    assert client.delete(f"/api/printers/{owner['p'].id}", headers=owner["h"]).status_code == 204
    db.expire_all()
    assert db.get(Printer, owner["p"].id).is_active is False
