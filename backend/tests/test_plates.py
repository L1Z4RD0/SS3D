"""Planchas adicionales y reimpresiones por fallo."""
from datetime import date
from decimal import Decimal

import pytest
from conftest import deliver, sale_payload

from app.models.filament import Filament
from app.models.printer import Printer


def _plate(printer, filament=None, grams=50, hours=1, name="Llaveros", **extra):
    body = {"name": name, "printer_id": str(printer.id), "print_hours": hours,
            "filaments": [{"filament_id": str(filament.id), "grams_used": grams}] if filament else []}
    body.update(extra)
    return body


@pytest.fixture
def shop(make):
    u = make.user()
    return {"u": u, "h": make.headers(u), "p1": make.printer(u, name="A1"), "p2": make.printer(u, name="Ender"),
            "f": make.filament(u, grams=1000)}


def _state(db, shop):
    db.expire_all()
    return (db.get(Filament, shop["f"].id).available_g, db.get(Printer, shop["p1"].id).hours_used,
            db.get(Printer, shop["p2"].id).hours_used)


def test_sale_with_extra_plate_on_other_printer(client, db, shop):
    h = shop["h"]
    single = client.post("/api/sales", headers=h, json=sale_payload(shop["p1"], shop["f"], 100, price=20000)).json()
    body = sale_payload(shop["p1"], shop["f"], 100, price=20000, extra_plates=[_plate(shop["p2"], shop["f"], 60, 3)])
    r = client.post("/api/sales", headers=h, json=body)
    assert r.status_code == 201, r.text
    sale = r.json()
    [plate] = sale["plates"]
    assert plate["printer_name"] == "Ender" and plate["is_reprint"] is False
    assert Decimal(plate["total_cost"]) > 0
    # El pedido completo cuesta la plancha principal + la adicional.
    assert Decimal(sale["total_cost"]) == Decimal(single["total_cost"]) + Decimal(plate["total_cost"])
    assert Decimal(sale["material_cost"]) == Decimal(single["material_cost"]) + Decimal(plate["material_cost"])
    assert Decimal(sale["grams_used"]) == 160
    # Filamento de ambas planchas y horas en cada impresora.
    assert _state(db, shop) == (Decimal(1000 - 100 - 100 - 60), Decimal(4), Decimal(3))


def test_quote_includes_plates_in_price(client, shop):
    h = shop["h"]
    base = {"printer_id": str(shop["p1"].id), "filaments": [{"filament_id": str(shop["f"].id), "grams_used": 100}],
            "print_hours": 2}
    one = client.post("/api/calculator/quote", headers=h, json=base).json()
    two = client.post("/api/calculator/quote", headers=h, json={**base, "extra_plates": [_plate(shop["p2"], shop["f"], 60, 3)]}).json()
    assert Decimal(two["breakdown"]["margin_base_cost"]) > Decimal(one["breakdown"]["margin_base_cost"])
    assert Decimal(two["scenarios"][0]["price"]) > Decimal(one["scenarios"][0]["price"])


def test_calculator_save_as_sale_with_plates(client, db, shop):
    body = {"printer_id": str(shop["p1"].id), "filaments": [{"filament_id": str(shop["f"].id), "grams_used": 100}],
            "print_hours": 2, "extra_plates": [_plate(shop["p2"], shop["f"], 60, 3)],
            "sale_date": str(date.today()), "client_name": "Portallaveros", "payment_method": "efectivo",
            "chosen_margin_percent": 90}
    r = client.post("/api/calculator/quote/save-as-sale", headers=shop["h"], json=body)
    assert r.status_code == 201, r.text
    assert len(r.json()["plates"]) == 1
    assert _state(db, shop) == (Decimal(840), Decimal(2), Decimal(3))


def test_reprint_during_production_adds_cost_not_price(client, db, shop):
    h = shop["h"]
    sale = client.post("/api/sales", headers=h, json=sale_payload(shop["p1"], shop["f"], 100, price=20000)).json()
    client.post(f"/api/sales/{sale['id']}/status", headers=h, json={"status": "en_produccion"})
    r = client.post(f"/api/sales/{sale['id']}/plates", headers=h,
                    json=_plate(shop["p1"], shop["f"], 30, 1, name="3 llaveros fallados", is_reprint=True))
    assert r.status_code == 201, r.text
    after = r.json()
    reprint = after["plates"][0]
    assert reprint["is_reprint"] is True
    assert Decimal(after["price"]) == Decimal(sale["price"])
    assert Decimal(after["total_cost"]) == Decimal(sale["total_cost"]) + Decimal(reprint["total_cost"])
    assert Decimal(after["profit"]) == Decimal(sale["profit"]) - Decimal(reprint["total_cost"])
    assert Decimal(after["reprint_cost"]) == Decimal(reprint["total_cost"])
    assert _state(db, shop) == (Decimal(870), Decimal(3), Decimal(0))

    # Quitarla (se agregó por error) deja todo como estaba.
    r = client.delete(f"/api/sales/{sale['id']}/plates/{reprint['id']}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["plates"] == []
    assert Decimal(r.json()["total_cost"]) == Decimal(sale["total_cost"])
    assert Decimal(r.json()["profit"]) == Decimal(sale["profit"])
    assert _state(db, shop) == (Decimal(900), Decimal(2), Decimal(0))


def test_cancel_and_delete_return_plate_consumption(client, db, shop):
    h = shop["h"]
    body = sale_payload(shop["p1"], shop["f"], 100, extra_plates=[_plate(shop["p2"], shop["f"], 60, 3)])
    sale = client.post("/api/sales", headers=h, json=body).json()
    assert client.post(f"/api/sales/{sale['id']}/cancel", headers=h, json={}).status_code == 200
    assert _state(db, shop) == (Decimal(1000), Decimal(0), Decimal(0))

    sale = client.post("/api/sales", headers=h, json=body).json()
    assert client.delete(f"/api/sales/{sale['id']}", headers=h).status_code == 204
    assert _state(db, shop) == (Decimal(1000), Decimal(0), Decimal(0))


def test_cancel_in_production_keeping_hours_keeps_plate_hours(client, db, shop):
    h = shop["h"]
    body = sale_payload(shop["p1"], shop["f"], 100, extra_plates=[_plate(shop["p2"], shop["f"], 60, 3)])
    sale = client.post("/api/sales", headers=h, json=body).json()
    client.post(f"/api/sales/{sale['id']}/status", headers=h, json={"status": "en_produccion"})
    r = client.post(f"/api/sales/{sale['id']}/cancel", headers=h,
                    json={"keep_hours": False, "piece_outcome": "inutilizable"})
    assert r.status_code == 200, r.text
    # Material usado (queda como pérdida), horas devueltas en ambas impresoras.
    assert _state(db, shop) == (Decimal(840), Decimal(0), Decimal(0))
    assert Decimal(r.json()["loss_amount"]) > 0


def test_full_edit_keeps_plates_and_their_cost(client, db, shop):
    h = shop["h"]
    body = sale_payload(shop["p1"], shop["f"], 100, extra_plates=[_plate(shop["p2"], shop["f"], 60, 3)])
    sale = client.post("/api/sales", headers=h, json=body).json()
    plate_cost = Decimal(sale["plates"][0]["total_cost"])
    r = client.put(f"/api/sales/{sale['id']}", headers=h,
                   json={"filaments": [{"filament_id": str(shop["f"].id), "grams_used": 200}]})
    assert r.status_code == 200, r.text
    edited = r.json()
    assert len(edited["plates"]) == 1
    only_main = Decimal(edited["total_cost"]) - plate_cost
    assert only_main > Decimal(sale["total_cost"]) - plate_cost  # la principal usa más material
    assert Decimal(edited["grams_used"]) == 260
    assert _state(db, shop)[0] == Decimal(1000 - 200 - 60)


def test_plate_rules(client, db, make, shop):
    h = shop["h"]
    other = make.user()
    foreign_printer = make.printer(other)
    sale = client.post("/api/sales", headers=h, json=sale_payload(shop["p1"], shop["f"], 100)).json()
    # Impresora de otro usuario: no existe para este pedido.
    assert client.post(f"/api/sales/{sale['id']}/plates", headers=h, json=_plate(foreign_printer)).status_code == 404
    # Filamento insuficiente: no se consume nada.
    r = client.post(f"/api/sales/{sale['id']}/plates", headers=h, json=_plate(shop["p2"], shop["f"], 5000))
    assert r.status_code == 400 and "Stock insuficiente" in r.text
    assert _state(db, shop) == (Decimal(900), Decimal(2), Decimal(0))
    # Entregado: ya no se agregan planchas.
    deliver(client, h, sale["id"])
    assert client.post(f"/api/sales/{sale['id']}/plates", headers=h, json=_plate(shop["p2"])).status_code == 409


def test_resources_used_only_in_plates_are_deactivated_not_deleted(client, db, shop):
    h = shop["h"]
    lonely = client.post("/api/inventory/filaments", headers=h, json={
        "brand": "Sunlu", "type": "PLA", "color": "Azul", "entry_date": str(date.today()),
        "initial_stock_g": 500, "min_alert_g": 50, "spool_price": 10000}).json()
    plate = {"name": "Base", "printer_id": str(shop["p2"].id), "print_hours": 1,
             "filaments": [{"filament_id": lonely["id"], "grams_used": 20}]}
    client.post("/api/sales", headers=h, json=sale_payload(shop["p1"], extra_plates=[plate]))
    assert client.delete(f"/api/inventory/filaments/{lonely['id']}", headers=h).status_code == 204
    assert client.delete(f"/api/printers/{shop['p2'].id}", headers=h).status_code == 204
    db.expire_all()
    assert db.get(Filament, lonely["id"]).is_active is False
    assert db.get(Printer, shop["p2"].id) is not None
