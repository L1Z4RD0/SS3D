"""Fase 3: Calendario (pedidos por fecha de entrega comprometida) y cambio de fecha."""
from datetime import date, timedelta
from decimal import Decimal

from conftest import deliver, sale_payload

from app.models.audit_log import AuditLog
from app.models.sale import Sale

TODAY = date.today()


def _new(client, h, printer, promised, **kw):
    r = client.post("/api/sales", headers=h, json=sale_payload(printer, promised_delivery_date=str(promised), **kw))
    assert r.status_code == 201, r.text
    return r.json()


def _cal(client, h, **params):
    r = client.get("/api/sales/calendar", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_calendar_places_orders_by_promised_date(client, make):
    u = make.user()
    h = make.headers(u)
    p = make.printer(u)
    inside = _new(client, h, p, TODAY + timedelta(days=3))
    _new(client, h, p, TODAY + timedelta(days=60))  # fuera del rango
    rows = _cal(client, h, date_from=str(TODAY), date_to=str(TODAY + timedelta(days=10)))
    assert [r["id"] for r in rows] == [inside["id"]]
    assert rows[0]["promised_delivery_date"] == str(TODAY + timedelta(days=3))
    assert rows[0]["status"] == "pendiente" and rows[0]["owner_username"] == u.username and rows[0]["can_edit"]


def test_cancelled_hidden_by_default(client, make, db):
    u = make.user()
    h = make.headers(u)
    p = make.printer(u)
    a = _new(client, h, p, TODAY)
    sale = db.get(Sale, a["id"])
    sale.status = "cancelado"
    db.commit()
    rng = {"date_from": str(TODAY), "date_to": str(TODAY)}
    assert _cal(client, h, **rng) == []
    assert [r["id"] for r in _cal(client, h, include_cancelled=True, **rng)] == [a["id"]]


def test_overdue_query(client, make):
    u = make.user()
    h = make.headers(u)
    p = make.printer(u)
    late = _new(client, h, p, TODAY - timedelta(days=4))
    done = _new(client, h, p, TODAY - timedelta(days=4))
    deliver(client, h, done["id"])
    rows = _cal(client, h, date_to=str(TODAY - timedelta(days=1)), status="abiertos")
    assert [r["id"] for r in rows] == [late["id"]]


def test_range_limit(client, make):
    u = make.user()
    r = client.get("/api/sales/calendar", headers=make.headers(u),
                   params={"date_from": str(TODAY), "date_to": str(TODAY + timedelta(days=200))})
    assert r.status_code == 400


def test_users_only_see_their_calendar(client, make):
    a, b = make.user(), make.user()
    _new(client, make.headers(a), make.printer(a), TODAY)
    assert _cal(client, make.headers(b), date_from=str(TODAY), date_to=str(TODAY)) == []


def test_watcher_sees_own_and_assigned_orders(client, make):
    owner, stranger = make.user(name="sntg"), make.user(name="ana")
    w = make.user("watcher", "olzer")
    make.assign(w, owner)
    op = make.printer(owner)
    by_owner = _new(client, make.headers(owner), op, TODAY)
    _new(client, make.headers(stranger), make.printer(stranger), TODAY)
    by_watcher = _new(client, make.headers(w), op, TODAY, owner_id=owner.id)
    rows = {r["id"]: r for r in _cal(client, make.headers(w), date_from=str(TODAY), date_to=str(TODAY))}
    assert set(rows) == {by_owner["id"], by_watcher["id"]}
    assert rows[by_owner["id"]]["can_edit"] is False and rows[by_watcher["id"]]["can_edit"] is True
    assert rows[by_watcher["id"]]["created_by_username"] == w.username
    assert rows[by_watcher["id"]]["owner_username"] == owner.username


# ---------------- Cambiar fecha de entrega ----------------

def test_change_delivery_date_only_moves_the_date(client, make, db):
    u = make.user()
    h = make.headers(u)
    p, f = make.printer(u), make.filament(u)
    a = _new(client, h, p, TODAY, filament=f)
    before = db.get(Sale, a["id"])
    cost_before = before.total_cost
    new_day = TODAY + timedelta(days=7)
    r = client.patch(f"/api/sales/{a['id']}/delivery-date", headers=h, json={"promised_delivery_date": str(new_day)})
    assert r.status_code == 200, r.text
    assert r.json()["promised_delivery_date"] == str(new_day)
    db.expire_all()
    after = db.get(Sale, a["id"])
    assert after.total_cost == cost_before and after.material_cost == before.material_cost
    ev = db.query(AuditLog).filter(AuditLog.entity_id == after.id,
                                   AuditLog.event_type == "SALE_DELIVERY_DATE_CHANGED").one()
    assert ev.details["promised_delivery_date"]["to"] == str(new_day)


def test_change_delivery_date_works_in_production(client, make):
    u = make.user()
    h = make.headers(u)
    a = _new(client, h, make.printer(u), TODAY)
    client.post(f"/api/sales/{a['id']}/status", headers=h, json={"status": "en_produccion"})
    r = client.patch(f"/api/sales/{a['id']}/delivery-date", headers=h,
                     json={"promised_delivery_date": str(TODAY + timedelta(days=2))})
    assert r.status_code == 200


def test_change_delivery_date_blocked_when_delivered(client, make):
    u = make.user()
    h = make.headers(u)
    a = _new(client, h, make.printer(u), TODAY)
    deliver(client, h, a["id"])
    r = client.patch(f"/api/sales/{a['id']}/delivery-date", headers=h,
                     json={"promised_delivery_date": str(TODAY + timedelta(days=2))})
    assert r.status_code == 409


def test_watcher_cannot_move_owners_orders(client, make):
    owner = make.user(name="sntg")
    w = make.user("watcher", "olzer")
    make.assign(w, owner)
    a = _new(client, make.headers(owner), make.printer(owner), TODAY)
    r = client.patch(f"/api/sales/{a['id']}/delivery-date", headers=make.headers(w),
                     json={"promised_delivery_date": str(TODAY + timedelta(days=2))})
    assert r.status_code == 404


def test_dashboard_unaffected_by_calendar_moves(client, make):
    u = make.user()
    h = make.headers(u)
    a = _new(client, h, make.printer(u), TODAY, price=5000)
    client.patch(f"/api/sales/{a['id']}/delivery-date", headers=h,
                 json={"promised_delivery_date": str(TODAY + timedelta(days=40))})
    assert client.get("/api/dashboard/summary", headers=h).json()["total_jobs"] == 0
    deliver(client, h, a["id"], TODAY)
    assert Decimal(client.get("/api/dashboard/summary", headers=h).json()["total_revenue"]) == 5000
