"""Fase 1: las ventas nuevas quedan registradas con estado, fechas e historial, sin
cambiar ninguna cifra (nacen Entregadas en su fecha de venta, igual que las migradas)."""
from datetime import date, timedelta

from conftest import sale_payload

from app.models.sale import Sale
from app.models.sale_status_history import SaleStatusHistory


def test_new_sale_starts_delivered_with_history(client, db, make):
    u = make.user()
    p = make.printer(u)
    r = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p))
    assert r.status_code == 201
    db.expire_all()
    sale = db.get(Sale, r.json()["id"])
    assert sale.status == "entregada"
    assert sale.promised_delivery_date == sale.delivered_date == sale.sale_date
    hist = db.query(SaleStatusHistory).filter(SaleStatusHistory.sale_id == sale.id).all()
    assert [(h.status, h.changed_by_user_id, h.is_migration) for h in hist] == [("entregada", u.id, False)]


def test_editing_sale_date_moves_delivery_dates(client, db, make):
    u = make.user()
    p = make.printer(u)
    sale = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p)).json()
    new_day = date.today() - timedelta(days=40)
    assert client.put(f"/api/sales/{sale['id']}", headers=make.headers(u),
                      json={"sale_date": str(new_day)}).status_code == 200
    db.expire_all()
    s = db.get(Sale, sale["id"])
    assert s.promised_delivery_date == s.delivered_date == new_day


def test_deleting_sale_removes_its_history(client, db, make):
    u = make.user()
    p = make.printer(u)
    sale = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p)).json()
    assert client.delete(f"/api/sales/{sale['id']}", headers=make.headers(u)).status_code == 204
    db.expire_all()
    assert db.query(SaleStatusHistory).filter(SaleStatusHistory.sale_id == sale["id"]).count() == 0
