"""Rehacer un pedido cuya pieza se dañó: al cancelar se crea uno igual, directo En producción."""
from decimal import Decimal

import pytest
from conftest import sale_payload

from app.models.filament import Filament
from app.models.printer import Printer
from app.models.supply import Supply


@pytest.fixture
def setup(client, make):
    """Pedido de 100 g (de 1000), 2 argollas (de 50), 2 h de impresión, fuente Instagram."""
    u = make.user()
    p, f, s = make.printer(u), make.filament(u), make.supply(u)
    h = make.headers(u)
    r = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100, s, 2, price=9000, sale_source="instagram",
                                                             buyer_name="Ana", notes="Color rojo"))
    assert r.status_code == 201, r.text
    return {"u": u, "h": h, "sale": r.json(), "p": p, "f": f, "s": s}


def _to(client, setup, *statuses):
    for st in statuses:
        r = client.post(f"/api/sales/{setup['sale']['id']}/status", headers=setup["h"], json={"status": st})
        assert r.status_code == 200, r.text


def _stock(db, setup):
    db.expire_all()
    return (db.get(Filament, setup["f"].id).available_g, db.get(Supply, setup["s"].id).quantity_available,
            db.get(Printer, setup["p"].id).hours_used)


def test_redo_unusable_piece_in_production(client, db, setup):
    _to(client, setup, "en_produccion")
    r = client.post(f"/api/sales/{setup['sale']['id']}/cancel", headers=setup["h"],
                    json={"keep_hours": True, "piece_outcome": "inutilizable", "redo": True})
    assert r.status_code == 200, r.text
    cancelled = r.json()
    assert cancelled["status"] == "cancelado" and cancelled["redone_as_id"]

    new = client.get(f"/api/sales/{cancelled['redone_as_id']}", headers=setup["h"]).json()
    assert new["status"] == "en_produccion"
    orig = setup["sale"]
    for field in ("client_name", "buyer_name", "price", "payment_method", "sale_source", "printer_id", "notes",
                  "promised_delivery_date", "print_hours", "material_cost"):
        assert new[field] == orig[field], field
    assert [h["status"] for h in new["status_history"]] == ["pendiente", "en_produccion"]
    assert "Rehecho del pedido" in new["status_history"][0]["note"]

    # Filamento: 100 g del pedido fallido + 100 g del nuevo. Insumos: se devolvieron al cancelar
    # y se vuelven a usar. Horas: 2 h registradas del fallido + 2 h del nuevo.
    assert _stock(db, setup) == (Decimal(800), Decimal(48), Decimal(4))


def test_redo_damaged_piece_when_ready(client, setup):
    _to(client, setup, "en_produccion", "lista")
    r = client.post(f"/api/sales/{setup['sale']['id']}/cancel", headers=setup["h"],
                    json={"keep_hours": True, "piece_outcome": "descartar", "discard_reason": "danada", "redo": True})
    assert r.status_code == 200, r.text
    new = client.get(f"/api/sales/{r.json()['redone_as_id']}", headers=setup["h"]).json()
    assert new["status"] == "en_produccion"


@pytest.mark.parametrize("statuses,body", [
    (("en_produccion",), {"piece_outcome": "almacen"}),
    (("en_produccion", "lista"), {"piece_outcome": "descartar", "discard_reason": "regalada"}),
    ((), {}),  # Pendiente
])
def test_redo_only_for_damaged_pieces(client, db, setup, statuses, body):
    _to(client, setup, *statuses)
    before = _stock(db, setup)
    r = client.post(f"/api/sales/{setup['sale']['id']}/cancel", headers=setup["h"], json={**body, "redo": True})
    assert r.status_code == 400
    # No se canceló nada.
    assert client.get(f"/api/sales/{setup['sale']['id']}", headers=setup["h"]).json()["status"] != "cancelado"
    assert _stock(db, setup) == before


def test_redo_without_stock_cancels_nothing(client, db, setup):
    _to(client, setup, "en_produccion")
    # Solo quedan 50 g: no alcanza para rehacer los 100 g.
    f = db.get(Filament, setup["f"].id)
    f.available_g = Decimal(50)
    db.commit()
    r = client.post(f"/api/sales/{setup['sale']['id']}/cancel", headers=setup["h"],
                    json={"keep_hours": True, "piece_outcome": "inutilizable", "redo": True})
    assert r.status_code == 400 and "Stock insuficiente" in r.text
    assert client.get(f"/api/sales/{setup['sale']['id']}", headers=setup["h"]).json()["status"] == "en_produccion"


def test_cancel_without_redo_unchanged(client, setup):
    _to(client, setup, "en_produccion")
    r = client.post(f"/api/sales/{setup['sale']['id']}/cancel", headers=setup["h"],
                    json={"keep_hours": True, "piece_outcome": "inutilizable"})
    assert r.status_code == 200 and r.json()["redone_as_id"] is None


def test_redo_keeps_registrant_for_company_sale(client, db, make):
    from app.models.user import User

    partner = make.user(name="diego")
    company = make.user("watcher", "empresa")
    db.get(User, company.id).is_company = True
    db.commit()
    make.assign(company, partner)
    hc = make.headers(company)
    body = sale_payload(make.printer(partner), make.filament(company), 50, price=12000, owner_id=company.id)
    s = client.post("/api/sales", headers=hc, json=body).json()
    client.post(f"/api/sales/{s['id']}/status", headers=hc, json={"status": "en_produccion"})
    r = client.post(f"/api/sales/{s['id']}/cancel", headers=hc,
                    json={"keep_hours": True, "piece_outcome": "inutilizable", "redo": True})
    assert r.status_code == 200, r.text
    new = client.get(f"/api/sales/{r.json()['redone_as_id']}", headers=hc).json()
    assert new["created_by_user_id"] == str(company.id) and new["owner_id"] == str(company.id)
