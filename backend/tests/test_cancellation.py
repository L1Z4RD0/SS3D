"""Fase 4: flujo de cancelación e ingreso de piezas al Almacén."""
from datetime import date
from decimal import Decimal

import pytest
from conftest import sale_payload

from app.models.audit_log import AuditLog
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import Sale
from app.models.supply import Supply
from app.models.warehouse_item import WarehouseItem


@pytest.fixture
def setup(client, make):
    """Pedido de 100 g (de 1000), 2 argollas (de 50), 2 h de impresión, 0,5 h de postprocesado."""
    u = make.user()
    p, f, s = make.printer(u), make.filament(u), make.supply(u)
    h = make.headers(u)
    r = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100, s, 2, price=9000))
    assert r.status_code == 201, r.text
    return {"u": u, "h": h, "sale": r.json(), "p": p, "f": f, "s": s}


def _to(client, setup, *statuses):
    for st in statuses:
        r = client.post(f"/api/sales/{setup['sale']['id']}/status", headers=setup["h"], json={"status": st})
        assert r.status_code == 200, r.text


def _cancel(client, setup, **body):
    return client.post(f"/api/sales/{setup['sale']['id']}/cancel", headers=setup["h"], json=body)


def _stock(db, setup):
    db.expire_all()
    return (db.get(Filament, setup["f"].id).available_g, db.get(Supply, setup["s"].id).quantity_available,
            db.get(Printer, setup["p"].id).hours_used)


def _pieces(db, sale_id):
    db.expire_all()
    return db.query(WarehouseItem).filter(WarehouseItem.origin_sale_id == sale_id).all()


# Costos del pedido de prueba: material 1000, depreciación 300, energía 114,80,
# postprocesado 2500, insumos 200, envío 3000.
MATERIAL, DEPR, ENERGY, POST, SUPPLIES = Decimal(1000), Decimal(300), Decimal("114.80"), Decimal(2500), Decimal(200)


def test_cancel_pending_returns_everything(client, db, setup):
    r = _cancel(client, setup, reason="El cliente se arrepintió")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "cancelado" and d["cancel_reason"] == "El cliente se arrepintió"
    assert Decimal(d["loss_amount"]) == 0 and d["warehouse_piece"] is None
    assert _stock(db, setup) == (Decimal(1000), Decimal(50), Decimal(0))
    assert d["status_history"][-1]["status"] == "cancelado"
    assert "Motivo: El cliente se arrepintió" in d["status_history"][-1]["note"]
    assert db.query(AuditLog).filter(AuditLog.entity_id == d["id"], AuditLog.event_type == "SALE_CANCELLED").count() == 1


def test_cancel_in_production_usable_piece_goes_to_warehouse(client, db, setup):
    _to(client, setup, "en_produccion")
    r = _cancel(client, setup, keep_hours=True, piece_outcome="almacen")
    assert r.status_code == 200, r.text
    # Filamento consumido, insumos devueltos, horas registradas
    assert _stock(db, setup) == (Decimal(900), Decimal(50), Decimal(2))
    piece = r.json()["warehouse_piece"]
    assert piece["status"] == "en_almacen"
    assert Decimal(piece["cost"]) == MATERIAL + POST + DEPR + ENERGY  # sin insumos ni envío
    assert Decimal(piece["price"]) == Decimal(9000)
    assert Decimal(r.json()["loss_amount"]) == 0
    item = _pieces(db, setup["sale"]["id"])[0]
    assert item.user_id == setup["u"].id and item.name == "Llavero" and item.entry_date == date.today()


def test_cancel_in_production_unusable_without_hours_is_loss(client, db, setup):
    _to(client, setup, "en_produccion")
    r = _cancel(client, setup, keep_hours=False, piece_outcome="inutilizable")
    assert r.status_code == 200, r.text
    assert _stock(db, setup) == (Decimal(900), Decimal(50), Decimal(0))  # horas devueltas
    assert Decimal(r.json()["loss_amount"]) == MATERIAL + POST  # sin depreciación/energía
    assert _pieces(db, setup["sale"]["id"]) == []


def test_cancel_ready_to_warehouse_consumes_supplies(client, db, setup):
    _to(client, setup, "en_produccion", "lista")
    r = _cancel(client, setup, keep_hours=True, piece_outcome="almacen")
    assert r.status_code == 200, r.text
    assert _stock(db, setup) == (Decimal(900), Decimal(48), Decimal(2))
    assert Decimal(r.json()["warehouse_piece"]["cost"]) == MATERIAL + POST + DEPR + ENERGY + SUPPLIES


def test_cancel_ready_discard_is_recorded_as_discarded_piece(client, db, setup):
    _to(client, setup, "en_produccion", "lista")
    assert _cancel(client, setup, piece_outcome="descartar").status_code == 400  # falta motivo
    r = _cancel(client, setup, keep_hours=True, piece_outcome="descartar", discard_reason="danada")
    assert r.status_code == 200, r.text
    item = _pieces(db, setup["sale"]["id"])[0]
    assert item.status == "descartada" and item.discard_reason == "danada" and item.discarded_at is not None
    # La pérdida queda en la pieza descartada (no duplicada en el pedido)
    assert Decimal(r.json()["loss_amount"]) == 0
    assert db.query(AuditLog).filter(AuditLog.entity_id == item.id,
                                     AuditLog.event_type == "WAREHOUSE_ITEM_DISCARDED").count() == 1


@pytest.mark.parametrize("status_path,body", [
    (("en_produccion",), {"keep_hours": True}),                                 # falta pieza
    (("en_produccion",), {"piece_outcome": "descartar"}),                       # opción de Lista
    (("en_produccion", "lista"), {"piece_outcome": "inutilizable"}),           # opción de En producción
])
def test_cancel_requires_valid_answers(client, db, setup, status_path, body):
    _to(client, setup, *status_path)
    assert _cancel(client, setup, **body).status_code == 400
    db.expire_all()
    assert db.get(Sale, setup["sale"]["id"]).status == status_path[-1]  # no cambió nada
    assert _stock(db, setup)[0] == Decimal(900)


def test_final_states_cannot_be_cancelled(client, setup):
    client.post(f"/api/sales/{setup['sale']['id']}/status", headers=setup["h"],
                json={"status": "entregada", "skip_confirmed": True})
    assert _cancel(client, setup).status_code == 409


def test_cancelled_twice_is_rejected(client, setup):
    assert _cancel(client, setup).status_code == 200
    assert _cancel(client, setup).status_code == 409


def test_cancelled_never_counts_as_income(client, setup):
    _cancel(client, setup)
    s = client.get("/api/dashboard/summary", headers=setup["h"]).json()
    assert s["total_jobs"] == 0 and Decimal(s["total_revenue"]) == 0


# ---------------- Eliminar un cancelado: nunca devuelve dos veces ----------------

def test_delete_cancelled_pending_does_not_double_return(client, db, setup):
    _cancel(client, setup)
    assert client.delete(f"/api/sales/{setup['sale']['id']}", headers=setup["h"]).status_code == 204
    assert _stock(db, setup) == (Decimal(1000), Decimal(50), Decimal(0))


def test_delete_cancelled_in_production_returns_only_what_remained(client, db, setup):
    _to(client, setup, "en_produccion")
    _cancel(client, setup, keep_hours=True, piece_outcome="inutilizable")
    assert client.delete(f"/api/sales/{setup['sale']['id']}", headers=setup["h"]).status_code == 204
    # filamento y horas vuelven ahora; los insumos ya habían vuelto al cancelar
    assert _stock(db, setup) == (Decimal(1000), Decimal(50), Decimal(0))


def test_delete_cancelled_with_piece_in_warehouse_removes_piece(client, db, setup):
    _to(client, setup, "en_produccion")
    _cancel(client, setup, piece_outcome="almacen")
    assert client.delete(f"/api/sales/{setup['sale']['id']}", headers=setup["h"]).status_code == 204
    assert _pieces(db, setup["sale"]["id"]) == []
    assert _stock(db, setup) == (Decimal(1000), Decimal(50), Decimal(0))


def test_delete_blocked_when_piece_reserved(client, db, setup):
    _to(client, setup, "en_produccion")
    _cancel(client, setup, piece_outcome="almacen")
    item = _pieces(db, setup["sale"]["id"])[0]
    item.status = "reservada"
    db.commit()
    assert client.delete(f"/api/sales/{setup['sale']['id']}", headers=setup["h"]).status_code == 409
    db.expire_all()
    assert db.get(Sale, setup["sale"]["id"]) is not None


# ---------------- Historial de recursos y permisos ----------------

def test_resources_used_in_cancelled_orders_are_deactivated_not_deleted(client, db, setup):
    _to(client, setup, "en_produccion")
    _cancel(client, setup, piece_outcome="almacen")
    h = setup["h"]
    for path in (f"/api/printers/{setup['p'].id}", f"/api/inventory/filaments/{setup['f'].id}",
                 f"/api/inventory/supplies/{setup['s'].id}"):
        assert client.delete(path, headers=h).status_code == 204
    db.expire_all()
    assert db.get(Printer, setup["p"].id).is_active is False
    assert db.get(Filament, setup["f"].id).is_active is False
    assert db.get(Supply, setup["s"].id).is_active is False


def test_watcher_cancels_only_what_he_registered(client, make):
    owner = make.user(name="sntg")
    w = make.user("watcher", "olzer")
    make.assign(w, owner)
    op = make.printer(owner)
    own = client.post("/api/sales", headers=make.headers(owner), json=sale_payload(op)).json()
    mine = client.post("/api/sales", headers=make.headers(w), json=sale_payload(op, owner_id=owner.id)).json()
    assert client.post(f"/api/sales/{own['id']}/cancel", headers=make.headers(w), json={}).status_code == 404
    assert client.post(f"/api/sales/{mine['id']}/cancel", headers=make.headers(w), json={}).status_code == 200
    # y la pieza que genere un pedido del observador es del dueño del inventario
    mine2 = client.post("/api/sales", headers=make.headers(w), json=sale_payload(op, owner_id=owner.id)).json()
    client.post(f"/api/sales/{mine2['id']}/status", headers=make.headers(w), json={"status": "en_produccion"})
    r = client.post(f"/api/sales/{mine2['id']}/cancel", headers=make.headers(w), json={"piece_outcome": "almacen"})
    assert r.status_code == 200
    assert r.json()["warehouse_piece"] is not None
