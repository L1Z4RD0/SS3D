"""Checklist de regresión: lo que ya funcionaba tiene que seguir funcionando igual."""
from datetime import date
from decimal import Decimal

from conftest import deliver, sale_payload

from app.models.audit_log import AuditLog
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.supply import Supply


def _refresh(db, *objs):
    db.expire_all()
    return [db.get(type(o), o.id) for o in objs]


def test_sale_consumes_and_delete_restores(client, db, make):
    u = make.user()
    p, f, s = make.printer(u), make.filament(u), make.supply(u)
    r = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p, f, 100, s, 2))
    assert r.status_code == 201, r.text
    p2, f2, s2 = _refresh(db, p, f, s)
    assert (f2.available_g, s2.quantity_available, p2.hours_used) == (Decimal(900), Decimal(48), Decimal(2))

    assert client.delete(f"/api/sales/{r.json()['id']}", headers=make.headers(u)).status_code == 204
    p3, f3, s3 = _refresh(db, p, f, s)
    assert (f3.available_g, s3.quantity_available, p3.hours_used) == (Decimal(1000), Decimal(50), Decimal(0))


def test_insufficient_stock_blocks_without_consuming(client, db, make):
    u = make.user()
    p, f, s = make.printer(u), make.filament(u, grams=50), make.supply(u, qty=1)
    r = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p, f, 100))
    assert r.status_code == 400 and "Stock insuficiente" in r.text
    r = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p, None, supply=s, qty=5))
    assert r.status_code == 400 and "Stock insuficiente" in r.text
    p2, f2, s2 = _refresh(db, p, f, s)
    assert (f2.available_g, s2.quantity_available, p2.hours_used) == (Decimal(50), Decimal(1), Decimal(0))


def test_edit_sale_rebalances_stock_and_keeps_price(client, db, make):
    u = make.user()
    p, f, s = make.printer(u), make.filament(u), make.supply(u)
    sale = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p, f, 100, s, 2)).json()
    r = client.put(
        f"/api/sales/{sale['id']}",
        headers=make.headers(u),
        json={"filaments": [{"filament_id": str(f.id), "grams_used": 250}], "print_hours": 5,
              "supplies": [{"supply_id": str(s.id), "quantity": 3}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["price"] == "9000.00"  # sin precio nuevo, se conserva
    p2, f2, s2 = _refresh(db, p, f, s)
    assert (f2.available_g, s2.quantity_available, p2.hours_used) == (Decimal(750), Decimal(47), Decimal(5))


def test_exhausted_filament_is_reported(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u, grams=100)
    r = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p, f, 100))
    assert r.status_code == 201
    assert [x["filament_id"] for x in r.json()["exhausted_filaments"]] == [str(f.id)]


def test_printer_life_unchanged_by_listing(client, db, make):
    u = make.user()
    p = make.printer(u)
    client.post("/api/sales", headers=make.headers(u), json=sale_payload(p))
    data = next(x for x in client.get("/api/printers", headers=make.headers(u)).json() if x["id"] == str(p.id))
    assert Decimal(data["life_used_percent"]) == Decimal("0.10")  # 2h de 2000h


def test_dashboard_and_history_count_sales(client, make):
    """Desde la Fase 2 una venta cuenta al entregarse (antes contaba al crearse)."""
    u = make.user()
    p = make.printer(u)
    today = date.today()
    a = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p, price=10000)).json()
    b = client.post("/api/sales", headers=make.headers(u),
                    json={**sale_payload(p, price=5000), "payment_method": "transferencia"}).json()
    deliver(client, make.headers(u), a["id"], today)
    deliver(client, make.headers(u), b["id"], today)
    s = client.get("/api/dashboard/summary", headers=make.headers(u),
                   params={"date_from": str(today), "date_to": str(today)}).json()
    assert s["total_jobs"] == 2 and Decimal(s["total_revenue"]) == Decimal(15000)
    pm = client.get("/api/dashboard/by-payment-method", headers=make.headers(u),
                    params={"date_from": str(today), "date_to": str(today)}).json()
    assert {x["payment_method"]: x["jobs"] for x in pm}["transferencia"] == 1
    h = client.get("/api/history/monthly", headers=make.headers(u)).json()
    assert h[0]["total_jobs"] == 2


def test_calculator_save_as_sale(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u)
    body = {"printer_id": str(p.id), "filaments": [{"filament_id": str(f.id), "grams_used": 100}],
            "print_hours": 2, "postprocess_hours": 0, "shipping_cost": 0, "supplies": [],
            "sale_date": str(date.today()), "client_name": "X", "payment_method": "efectivo",
            "chosen_margin_percent": 140}
    r = client.post("/api/calculator/quote/save-as-sale", headers=make.headers(u), json=body)
    assert r.status_code == 201, r.text


def test_quote_numbering_is_monotonic(client, make):
    u = make.user()
    item = {"client_name": "C", "quote_date": str(date.today()),
            "items": [{"description": "Llavero", "quantity": 2, "unit_price": 7500}]}
    q1 = client.post("/api/quotes", headers=make.headers(u), json=item).json()
    q2 = client.post("/api/quotes", headers=make.headers(u), json=item).json()
    assert (q1["quote_number"], q2["quote_number"]) == (1, 2)
    assert q1["total"] == "15000.00"


def test_users_do_not_see_each_other(client, make):
    a, b = make.user(), make.user()
    p = make.printer(a)
    sale = client.post("/api/sales", headers=make.headers(a), json=sale_payload(p)).json()
    assert client.get("/api/sales", headers=make.headers(b)).json()["total"] == 0
    assert client.get(f"/api/sales/{sale['id']}", headers=make.headers(b)).status_code == 404
    assert client.delete(f"/api/sales/{sale['id']}", headers=make.headers(b)).status_code == 404
    assert client.get("/api/inventory/filaments", headers=make.headers(b)).json() == []


def test_watcher_cannot_mix_inventories_or_touch_others(client, make):
    owner, other = make.user(name="sntg"), make.user(name="ana")
    w = make.user("watcher", "olzer")
    make.assign(w, owner)
    make.assign(w, other)
    op, of = make.printer(owner), make.filament(owner)
    xf = make.filament(other)
    # Mezclar inventarios en una venta: rechazado
    r = client.post("/api/sales", headers=make.headers(w), json=sale_payload(op, xf, owner_id=owner.id))
    assert r.status_code == 404
    # Venta válida para el dueño
    r = client.post("/api/sales", headers=make.headers(w), json=sale_payload(op, of, owner_id=owner.id))
    assert r.status_code == 201
    assert r.json()["created_by_username"] == w.username and r.json()["owner_username"] == owner.username
    # No puede tocar la venta que hizo el dueño
    own = client.post("/api/sales", headers=make.headers(owner), json=sale_payload(op)).json()
    assert client.put(f"/api/sales/{own['id']}", headers=make.headers(w), json={"notes": "x"}).status_code == 404
    # No puede modificar inventario ni impresoras
    assert client.delete(f"/api/printers/{op.id}", headers=make.headers(w)).status_code == 403


def test_filament_used_only_in_multicolor_is_deactivated_not_deleted(client, db, make):
    """Corrige el error: antes intentaba borrarlo y fallaba."""
    u = make.user()
    p, f1, f2 = make.printer(u), make.filament(u, color="Rojo"), make.filament(u, color="Azul")
    body = sale_payload(p)
    body["filaments"] = [{"filament_id": str(f1.id), "grams_used": 50}, {"filament_id": str(f2.id), "grams_used": 50}]
    assert client.post("/api/sales", headers=make.headers(u), json=body).status_code == 201
    assert client.delete(f"/api/inventory/filaments/{f1.id}", headers=make.headers(u)).status_code == 204
    db.expire_all()
    f1_db = db.get(Filament, f1.id)
    assert f1_db is not None and f1_db.is_active is False


def test_unused_resources_are_really_deleted(client, db, make):
    u = make.user()
    p_id, f_id, s_id = make.printer(u).id, make.filament(u).id, make.supply(u).id
    headers = make.headers(u)
    for path in (f"/api/printers/{p_id}", f"/api/inventory/filaments/{f_id}", f"/api/inventory/supplies/{s_id}"):
        assert client.delete(path, headers=headers).status_code == 204
    db.expire_all()
    assert db.get(Printer, p_id) is None and db.get(Filament, f_id) is None and db.get(Supply, s_id) is None


def test_audit_records_sale_events(client, db, make):
    u = make.user()
    p = make.printer(u)
    sale = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p)).json()
    client.delete(f"/api/sales/{sale['id']}", headers=make.headers(u))
    events = {e.event_type for e in db.query(AuditLog).filter(AuditLog.user_id == u.id)}
    assert {"SALE_CREATED", "SALE_DELETED"} <= events
