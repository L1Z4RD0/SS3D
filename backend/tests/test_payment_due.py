"""Pedidos "Por cobrar": al entregarlos es obligatorio decir cómo pagó o, si aún no paga,
hasta cuándo tiene plazo. El Reparto los cuenta el mes en que se cobran."""
from datetime import date
from decimal import Decimal

from conftest import deliver, sale_payload
from test_company import biz  # noqa: F401  (fixture)

OCT = date(2027, 10, 20)
NOV = date(2027, 11, 3)


def _status(client, h, sid, **body):
    return client.post(f"/api/sales/{sid}/status", headers=h, json={"skip_confirmed": True, **body})


def _unpaid_sale(client, h, printer, price=8000):
    r = client.post("/api/sales", headers=h, json=sale_payload(printer, price=price, payment_method="por_cobrar"))
    assert r.status_code == 201, r.text
    return r.json()


def test_unpaid_delivery_requires_method_or_due_date(client, make):
    u = make.user()
    h = make.headers(u)
    s = _unpaid_sale(client, h, make.printer(u))
    # Sigue "Por cobrar" en producción y en Lista.
    for step in ("en_produccion", "lista"):
        r = _status(client, h, s["id"], status=step)
        assert r.status_code == 200 and r.json()["payment_method"] == "por_cobrar"
    r = _status(client, h, s["id"], status="entregada", today=str(OCT))
    assert r.status_code == 400 and "fecha máxima de pago" in r.json()["detail"]
    r = _status(client, h, s["id"], status="entregada", today=str(OCT), payment_due_date="2027-10-19")
    assert r.status_code == 400  # plazo en el pasado
    assert client.get(f"/api/sales/{s['id']}", headers=h).json()["status"] == "lista"  # no se tocó nada


def test_paid_at_delivery(client, make):
    u = make.user()
    h = make.headers(u)
    s = _unpaid_sale(client, h, make.printer(u))
    r = _status(client, h, s["id"], status="entregada", today=str(OCT), payment_method="transferencia")
    assert r.status_code == 200, r.text
    sale = r.json()
    assert sale["payment_method"] == "transferencia" and sale["paid_date"] == str(OCT)
    assert sale["payment_due_date"] is None
    assert "Pagó al entregar: transferencia" in sale["status_history"][-1]["note"]


def test_delivered_unpaid_with_due_date_then_paid(client, make):
    u = make.user()
    h = make.headers(u)
    s = _unpaid_sale(client, h, make.printer(u))
    sale = deliver(client, h, s["id"], OCT, payment_due_date=date(2027, 11, 12))
    assert sale["payment_method"] == "por_cobrar" and sale["payment_due_date"] == "2027-11-12"
    assert "cobrar el 12 de noviembre" in sale["status_history"][-1]["note"]

    r = client.post(f"/api/sales/{s['id']}/payment", headers=h,
                    json={"payment_method": "efectivo", "paid_date": "2027-10-01"})
    assert r.status_code == 400  # antes de la entrega
    r = client.post(f"/api/sales/{s['id']}/payment", headers=h,
                    json={"payment_method": "efectivo", "paid_date": str(NOV)})
    assert r.status_code == 200, r.text
    assert r.json()["payment_method"] == "efectivo" and r.json()["paid_date"] == str(NOV)
    assert "Pago registrado: efectivo" in r.json()["status_history"][-1]["note"]
    # Ya cobrado: no se registra dos veces.
    assert client.post(f"/api/sales/{s['id']}/payment", headers=h,
                       json={"payment_method": "efectivo"}).status_code == 409


def test_payment_fields_ignored_when_not_unpaid(client, make):
    u = make.user()
    h = make.headers(u)
    s = client.post("/api/sales", headers=h, json=sale_payload(make.printer(u))).json()
    sale = deliver(client, h, s["id"], OCT, payment_method="transferencia")
    assert sale["payment_method"] == "efectivo" and sale["paid_date"] is None


def test_undo_delivery_returns_to_unpaid(client, make):
    u = make.user()
    h = make.headers(u)
    s = _unpaid_sale(client, h, make.printer(u))
    deliver(client, h, s["id"], OCT, payment_method="efectivo")
    r = _status(client, h, s["id"], status="lista")
    assert r.status_code == 200
    assert r.json()["payment_method"] == "por_cobrar" and r.json()["paid_date"] is None
    # Al entregarlo otra vez se vuelve a pedir el pago.
    assert _status(client, h, s["id"], status="entregada", today=str(OCT)).status_code == 400


def test_editing_payment_method_of_delivered_unpaid_marks_it_paid(client, make):
    u = make.user()
    h = make.headers(u)
    s = _unpaid_sale(client, h, make.printer(u))
    deliver(client, h, s["id"], OCT, payment_due_date=OCT)
    r = client.put(f"/api/sales/{s['id']}", headers=h, json={"payment_method": "transferencia"})
    assert r.status_code == 200, r.text
    assert r.json()["paid_date"] == str(date.today())


def test_split_counts_unpaid_in_the_month_it_is_collected(client, biz, monkeypatch):  # noqa: F811
    from app.config import settings

    monkeypatch.setattr(settings, "split_partners", f"{biz['diego'].username},{biz['sntg'].username}")
    h = biz["hd"]
    s = _unpaid_sale(client, h, biz["pd"], price=8000)
    deliver(client, h, s["id"], OCT, payment_due_date=date(2027, 11, 10))

    def split(month):
        r = client.get("/api/beta/split", headers=biz["hc"], params={"month": month})
        assert r.status_code == 200, r.text
        return r.json()

    octo = split("2027-10")
    assert Decimal(octo["collected_revenue"]) == 0
    assert [p["payment_due_date"] for p in octo["pending"]] == ["2027-11-10"]

    client.post(f"/api/sales/{s['id']}/payment", headers=h, json={"payment_method": "efectivo", "paid_date": str(NOV)})
    octo, nov = split("2027-10"), split("2027-11")
    # Octubre no cambia: sigue fuera, ahora con la fecha en que se cobró.
    assert Decimal(octo["collected_revenue"]) == 0 and octo["pending"][0]["paid_date"] == str(NOV)
    # Noviembre lo cuenta como cobrado, con los costos devueltos a su dueño.
    assert Decimal(nov["collected_revenue"]) == Decimal(s["price"])
    assert [l["paid_date"] for l in nov["sales"]] == [str(NOV)]
    assert not nov["pending"]

    # El Excel del Reparto sigue generándose con la fecha de cobro.
    r = client.get("/api/beta/split/export.xlsx", headers=biz["hc"], params={"month": "2027-10"})
    assert r.status_code == 200, r.text


def test_calculator_sale_keeps_delivery_person(client, make):
    u = make.user()
    h = make.headers(u)
    p = make.printer(u)
    body = {"printer_id": str(p.id), "filaments": [], "print_hours": 1, "postprocess_hours": 0,
            "shipping_cost": 2500, "supplies": [], "sale_date": str(date.today()), "client_name": "Con delivery",
            "payment_method": "efectivo", "chosen_margin_percent": 140, "delivery_by": "  Omar "}
    r = client.post("/api/calculator/quote/save-as-sale", headers=h, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["delivery_by"] == "Omar" and Decimal(r.json()["shipping_cost"]) == 2500
