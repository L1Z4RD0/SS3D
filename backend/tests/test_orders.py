"""Fase 2: pedidos con estados, transiciones, edición según estado y Dashboard solo con Entregadas."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from conftest import deliver, sale_payload

from app.models.audit_log import AuditLog
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import Sale


def _status(client, headers, sale_id, target, **kw):
    return client.post(f"/api/sales/{sale_id}/status", headers=headers, json={"status": target, **kw})


@pytest.fixture
def order(client, make):
    u = make.user()
    p, f, s = make.printer(u), make.filament(u), make.supply(u)
    promised = date.today() + timedelta(days=5)
    r = client.post("/api/sales", headers=make.headers(u),
                    json=sale_payload(p, f, 100, s, 2, promised_delivery_date=str(promised)))
    assert r.status_code == 201, r.text
    return {"user": u, "h": make.headers(u), "sale": r.json(), "printer": p, "filament": f, "supply": s,
            "promised": promised}


# ---------------- Creación ----------------

def test_new_order_is_pending_and_consumes_like_before(order, db):
    s = order["sale"]
    assert s["status"] == "pendiente" and s["delivered_date"] is None
    assert s["promised_delivery_date"] == str(order["promised"])
    db.expire_all()
    assert db.get(Filament, order["filament"].id).available_g == Decimal(900)
    assert db.get(Printer, order["printer"].id).hours_used == Decimal(2)


def test_promised_date_defaults_to_order_date(client, make):
    """Compatibilidad: una app vieja en caché no manda fecha de entrega."""
    u = make.user()
    p = make.printer(u)
    r = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p))
    assert r.json()["promised_delivery_date"] == r.json()["sale_date"]


def test_calculator_creates_pending_order_with_promised_date(client, make):
    u = make.user()
    p = make.printer(u)
    promised = date.today() + timedelta(days=3)
    body = {"printer_id": str(p.id), "filaments": [], "print_hours": 1, "postprocess_hours": 0, "shipping_cost": 0,
            "supplies": [], "sale_date": str(date.today()), "client_name": "X", "payment_method": "efectivo",
            "chosen_margin_percent": 140, "promised_delivery_date": str(promised)}
    r = client.post("/api/calculator/quote/save-as-sale", headers=make.headers(u), json=body)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pendiente" and r.json()["promised_delivery_date"] == str(promised)


def test_history_records_creation(client, order):
    d = client.get(f"/api/sales/{order['sale']['id']}", headers=order["h"]).json()
    assert [(h["status"], h["changed_by_username"]) for h in d["status_history"]] == [
        ("pendiente", order["user"].username)
    ]


# ---------------- Transiciones ----------------

def test_normal_flow_and_back_step(client, order):
    sid, h = order["sale"]["id"], order["h"]
    assert _status(client, h, sid, "en_produccion").json()["status"] == "en_produccion"
    assert _status(client, h, sid, "lista").json()["status"] == "lista"
    back = _status(client, h, sid, "en_produccion").json()
    assert back["status"] == "en_produccion"
    assert back["status_history"][-1]["note"] == "Retroceso de estado"
    _status(client, h, sid, "lista")
    today = date.today() - timedelta(days=1)
    d = _status(client, h, sid, "entregada", today=str(today)).json()
    assert d["status"] == "entregada" and d["delivered_date"] == str(today)
    assert [x["status"] for x in d["status_history"]] == [
        "pendiente", "en_produccion", "lista", "en_produccion", "lista", "entregada"]


def test_back_step_does_not_touch_inventory(client, order, db):
    sid, h = order["sale"]["id"], order["h"]
    _status(client, h, sid, "en_produccion")
    _status(client, h, sid, "pendiente")
    db.expire_all()
    assert db.get(Filament, order["filament"].id).available_g == Decimal(900)


def test_direct_delivery_needs_confirmation_and_records_steps(client, order):
    sid, h = order["sale"]["id"], order["h"]
    r = _status(client, h, sid, "entregada")
    assert r.status_code == 409 and "confírmalo" in r.text
    d = _status(client, h, sid, "entregada", skip_confirmed=True).json()
    steps = [x for x in d["status_history"] if x["status"] != "pendiente"]
    assert [x["status"] for x in steps] == ["en_produccion", "lista", "entregada"]
    assert len({x["changed_at"] for x in steps}) == 1  # misma hora


@pytest.mark.parametrize("bad", ["lista", "pendiente"])
def test_invalid_jumps_are_rejected(client, order, bad):
    sid, h = order["sale"]["id"], order["h"]
    if bad == "pendiente":
        r = _status(client, h, sid, "pendiente")  # ya está pendiente
    else:
        r = _status(client, h, sid, "lista")  # saltar un paso sin ser entrega directa
    assert r.status_code == 400


def test_final_states_cannot_change(client, order):
    sid, h = order["sale"]["id"], order["h"]
    deliver(client, h, sid)
    assert _status(client, h, sid, "lista").status_code == 409


def test_cancel_goes_through_cancel_flow(client, order):
    r = _status(client, order["h"], order["sale"]["id"], "cancelado")
    assert r.status_code == 400 and "Cancelar" in r.text


# ---------------- Dashboard / Historial ----------------

def test_dashboard_counts_only_delivered_by_real_date(client, make):
    u = make.user()
    h = make.headers(u)
    p = make.printer(u)
    today = date.today()
    last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=10)
    a = client.post("/api/sales", headers=h, json={**sale_payload(p, price=10000), "sale_date": str(last_month),
                                                  "payment_method": "transferencia"}).json()
    client.post("/api/sales", headers=h, json=sale_payload(p, price=7000))  # queda pendiente
    rng = {"date_from": str(today.replace(day=1)), "date_to": str(today)}
    assert client.get("/api/dashboard/summary", headers=h, params=rng).json()["total_jobs"] == 0

    # Pedido de un mes, entregado este mes: cuenta en el mes de la entrega.
    deliver(client, h, a["id"], today)
    s = client.get("/api/dashboard/summary", headers=h, params=rng).json()
    assert s["total_jobs"] == 1 and Decimal(s["total_revenue"]) == Decimal(10000)
    pm = client.get("/api/dashboard/by-payment-method", headers=h, params=rng).json()
    assert pm == [{"payment_method": "transferencia", "jobs": 1, "revenue": "10000.00", "profit": pm[0]["profit"]}]
    months = client.get("/api/history/monthly", headers=h).json()
    assert [(m["year"], m["month"], m["total_jobs"]) for m in months] == [(today.year, today.month, 1)]


# ---------------- Edición según estado ----------------

def test_pending_edits_everything(client, order, db):
    sid, h = order["sale"]["id"], order["h"]
    new_promised = date.today() + timedelta(days=9)
    r = client.put(f"/api/sales/{sid}", headers=h, json={
        "print_hours": 4, "promised_delivery_date": str(new_promised),
        "filaments": [{"filament_id": str(order["filament"].id), "grams_used": 150}]})
    assert r.status_code == 200, r.text
    assert r.json()["promised_delivery_date"] == str(new_promised)
    db.expire_all()
    assert db.get(Filament, order["filament"].id).available_g == Decimal(850)


def test_in_production_only_edits_order_data(client, order, db):
    sid, h = order["sale"]["id"], order["h"]
    _status(client, h, sid, "en_produccion")
    before = client.get(f"/api/sales/{sid}", headers=h).json()

    r = client.put(f"/api/sales/{sid}", headers=h, json={"print_hours": 9})
    assert r.status_code == 409 and "horas de impresión" in r.text
    r = client.put(f"/api/sales/{sid}", headers=h,
                   json={"filaments": [{"filament_id": str(order["filament"].id), "grams_used": 300}]})
    assert r.status_code == 409 and "filamentos" in r.text

    # Reenviar los mismos materiales (como hace la app) no es un cambio.
    same = {"filaments": [{"filament_id": str(order["filament"].id), "grams_used": 100}],
            "supplies": [{"supply_id": str(order["supply"].id), "quantity": 2}], "print_hours": 2,
            "price": 12000, "payment_method": "transferencia", "client_name": "Nuevo nombre",
            "buyer_name": "Cliente", "notes": "urgente",
            "promised_delivery_date": str(date.today() + timedelta(days=2))}
    r = client.put(f"/api/sales/{sid}", headers=h, json=same)
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["price"], d["payment_method"], d["client_name"], d["notes"]) == (
        "12000.00", "transferencia", "Nuevo nombre", "urgente")
    assert d["total_cost"] == before["total_cost"]  # costos intactos
    assert Decimal(d["profit"]) == Decimal(12000) - Decimal(before["total_cost"])
    db.expire_all()
    assert db.get(Filament, order["filament"].id).available_g == Decimal(900)


def test_delivered_edits_like_before_and_real_date(client, order):
    sid, h = order["sale"]["id"], order["h"]
    deliver(client, h, sid)
    new_real = date.today() - timedelta(days=3)
    r = client.put(f"/api/sales/{sid}", headers=h, json={"delivered_date": str(new_real), "print_hours": 3})
    assert r.status_code == 200, r.text
    assert r.json()["delivered_date"] == str(new_real) and r.json()["print_hours"] == "3.00"
    r = client.put(f"/api/sales/{sid}", headers=h,
                   json={"promised_delivery_date": str(date.today() + timedelta(days=30))})
    assert r.status_code == 400


def test_real_date_only_for_delivered(client, order):
    r = client.put(f"/api/sales/{order['sale']['id']}", headers=order["h"],
                   json={"delivered_date": str(date.today())})
    assert r.status_code == 400


def test_cancelled_cannot_be_edited(client, order, db):
    sale = db.get(Sale, order["sale"]["id"])
    sale.status = "cancelado"
    db.commit()
    r = client.put(f"/api/sales/{order['sale']['id']}", headers=order["h"], json={"notes": "x"})
    assert r.status_code == 409


def test_delete_still_undoes_everything_in_any_open_state(client, order, db):
    sid, h = order["sale"]["id"], order["h"]
    _status(client, h, sid, "en_produccion")
    assert client.delete(f"/api/sales/{sid}", headers=h).status_code == 204
    db.expire_all()
    assert db.get(Filament, order["filament"].id).available_g == Decimal(1000)
    assert db.get(Printer, order["printer"].id).hours_used == Decimal(0)


# ---------------- Listado, filtro y Observador ----------------

def test_status_filter(client, make):
    u = make.user()
    h = make.headers(u)
    p = make.printer(u)
    a = client.post("/api/sales", headers=h, json=sale_payload(p)).json()
    client.post("/api/sales", headers=h, json=sale_payload(p))
    deliver(client, h, a["id"])
    assert client.get("/api/sales", headers=h, params={"status": "entregada"}).json()["total"] == 1
    assert client.get("/api/sales", headers=h, params={"status": "abiertos"}).json()["total"] == 1
    assert client.get("/api/sales", headers=h, params={"status": "raro"}).status_code == 400


def test_watcher_sees_assigned_orders_read_only(client, make):
    owner, stranger = make.user(name="sntg"), make.user(name="ana")
    w = make.user("watcher", "olzer")
    make.assign(w, owner)
    op, sp = make.printer(owner), make.printer(stranger)
    own = client.post("/api/sales", headers=make.headers(owner), json=sale_payload(op)).json()
    client.post("/api/sales", headers=make.headers(stranger), json=sale_payload(sp))
    mine = client.post("/api/sales", headers=make.headers(w), json=sale_payload(op, owner_id=owner.id)).json()

    listed = {x["id"]: x["can_edit"] for x in client.get("/api/sales", headers=make.headers(w)).json()["items"]}
    assert listed == {own["id"]: False, mine["id"]: True}  # nada del usuario no asignado
    # No puede cambiar estado ni editar el pedido que hizo el dueño
    assert _status(client, make.headers(w), own["id"], "en_produccion").status_code == 404
    assert client.put(f"/api/sales/{own['id']}", headers=make.headers(w), json={"notes": "x"}).status_code == 404
    # Sí el suyo
    assert _status(client, make.headers(w), mine["id"], "en_produccion").status_code == 200
    # El dueño puede con todos los suyos, incluido el que registró el observador
    owner_view = {x["id"]: x["can_edit"] for x in client.get("/api/sales", headers=make.headers(owner)).json()["items"]}
    assert owner_view == {own["id"]: True, mine["id"]: True}
    assert _status(client, make.headers(owner), mine["id"], "lista").status_code == 200


def test_watcher_dashboard_counts_only_what_he_registered(client, make):
    owner = make.user(name="sntg")
    w = make.user("watcher", "olzer")
    make.assign(w, owner)
    op = make.printer(owner)
    own = client.post("/api/sales", headers=make.headers(owner), json=sale_payload(op, price=5000)).json()
    mine = client.post("/api/sales", headers=make.headers(w), json=sale_payload(op, owner_id=owner.id, price=8000)).json()
    deliver(client, make.headers(owner), own["id"])
    deliver(client, make.headers(w), mine["id"])
    assert Decimal(client.get("/api/dashboard/summary", headers=make.headers(w)).json()["total_revenue"]) == 8000
    assert Decimal(client.get("/api/dashboard/summary", headers=make.headers(owner)).json()["total_revenue"]) == 13000


def test_audit_records_status_and_date_changes(client, order, db):
    sid, h = order["sale"]["id"], order["h"]
    _status(client, h, sid, "en_produccion")
    client.put(f"/api/sales/{sid}", headers=h, json={"promised_delivery_date": str(date.today() + timedelta(days=20))})
    events = {e.event_type for e in db.query(AuditLog).filter(AuditLog.entity_id == sid)}
    assert {"SALE_CREATED", "SALE_STATUS_CHANGED", "SALE_DELIVERY_DATE_CHANGED"} <= events
