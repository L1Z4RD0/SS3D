"""Rendimiento por cuenta (solo Empresa): ingresos (sin delivery) al dueño de la venta (el de la impresora),
"registradas" a quien la ingresó, costos a quien puso cada recurso y "todas
juntas" sin contar dos veces una venta."""
from datetime import date
from decimal import Decimal


def num(v) -> Decimal:
    """Montos de la respuesta JSON (números) a Decimal exacto."""
    return Decimal(str(v))

import pytest
from conftest import deliver, sale_payload

from app.models.user import User


@pytest.fixture
def biz(db, make):
    diego, sntg = make.user(name="diego"), make.user(name="sntg")
    company = make.user("watcher", "empresa")
    db.get(User, company.id).is_company = True
    db.commit()
    make.assign(company, diego)
    make.assign(company, sntg)
    return {"diego": diego, "sntg": sntg, "company": company,
            "hd": make.headers(diego), "hs": make.headers(sntg), "hc": make.headers(company),
            "pd": make.printer(diego), "fd": make.filament(diego), "ps": make.printer(sntg),
            "fc": make.filament(company, color="Negro")}


def _perf(client, h, **params):
    r = client.get("/api/performance", headers=h, params=params)
    assert r.status_code == 200, r.text
    data = r.json()
    return data, {a["username"]: a for a in data["accounts"]}


def test_only_company_sees_performance(client, make, biz):
    assert client.get("/api/performance", headers=biz["hd"]).status_code == 403
    assert client.get("/api/performance", headers=make.headers(make.user())).status_code == 403


def test_revenue_to_owner_managed_to_registrant_costs_to_resource_owner(client, biz):
    today = date.today()
    # Diego vende con lo suyo.
    a = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], biz["fd"], 100, price=20000)).json()
    deliver(client, biz["hd"], a["id"], today)
    # La Empresa registra una venta con la impresora de Diego y SU filamento: es de Diego.
    body = sale_payload(biz["pd"], biz["fc"], 50, price=15000, owner_id=biz["company"].id)
    b = client.post("/api/sales", headers=biz["hc"], json=body)
    assert b.status_code == 201, b.text
    b = b.json()
    deliver(client, biz["hc"], b["id"], today)
    # Pedido abierto: no cuenta.
    client.post("/api/sales", headers=biz["hc"], json=sale_payload(biz["pd"], price=99999, owner_id=biz["company"].id))

    data, acc = _perf(client, biz["hc"], date_from=str(today), date_to=str(today))
    D, C, S = biz["diego"].username, biz["company"].username, biz["sntg"].username
    assert [a["username"] for a in data["accounts"]] == sorted([D, S], key=str.lower) + [C]  # Empresa al final

    # Ingresos: las dos ventas son de Diego; la Empresa solo gestionó una.
    assert num(acc[D]["sales"]["revenue"]) == 35000 - 2 * 3000 and acc[D]["sales"]["jobs"] == 2  # sin el delivery ($3.000 de sale_payload), que va aparte
    assert num(acc[C]["sales"]["revenue"]) == 0 and acc[C]["sales"]["jobs"] == 0
    # Registradas: cada cuenta, las que ingresó ella (propias o de otra cuenta).
    assert acc[C]["managed"]["jobs"] == 1 and num(acc[C]["managed"]["revenue"]) == 15000 - 3000
    assert acc[D]["managed"]["jobs"] == 1 and acc[S]["managed"]["jobs"] == 0 and acc[S]["sales"]["jobs"] == 0

    # Costos: la máquina de ambas ventas es de Diego; el material de B es de la Empresa.
    machine_b = Decimal(b["depreciation_cost"]) + Decimal(b["energy_cost"])
    machine_a = Decimal(a["depreciation_cost"]) + Decimal(a["energy_cost"])
    assert num(acc[D]["own_costs"]["machine"]) == machine_a + machine_b
    assert num(acc[D]["own_costs"]["material"]) == Decimal(a["material_cost"])
    assert num(acc[C]["own_costs"]["machine"]) == 0
    assert num(acc[C]["own_costs"]["material"]) == Decimal(b["material_cost"])
    assert acc[D]["own_costs"]["sales_with_resources"] == 2
    assert num(acc[D]["own_costs"]["print_hours"]) == 4  # 2 h + 2 h en su impresora
    assert num(acc[C]["own_costs"]["filament_g"]) == 50

    # Todas juntas: cada venta una sola vez.
    combined = data["combined"]
    assert combined["jobs"] == 2 and num(combined["revenue"]) == 35000 - 2 * 3000 and num(combined["shared_cost"]) == 2 * 3000
    assert combined["mixed_sales"] == 1  # B usó el filamento de la Empresa
    assert len(data["months"]) == 1
    month = data["months"][0]
    assert month["combined"]["jobs"] == 2
    assert num(month["accounts"][str(biz["diego"].id)]["own_cost"]) == num(acc[D]["own_costs"]["total"])
    assert month["accounts"][str(biz["company"].id)]["managed_jobs"] == 1


def test_old_company_sale_with_partner_printer_counts_for_the_partner(client, db, biz):
    """Antes del 2026-11-05 la Empresa podía quedar como dueña de una venta hecha con la
    impresora de un socio: Rendimiento la cuenta del socio igual."""
    from app.models.sale import Sale

    today = date.today()
    s = client.post("/api/sales", headers=biz["hc"], json=sale_payload(biz["ps"], price=9000)).json()
    deliver(client, biz["hc"], s["id"], today)
    db.get(Sale, s["id"]).user_id = biz["company"].id  # como quedaban antes
    db.commit()
    _, acc = _perf(client, biz["hc"], date_from=str(today), date_to=str(today))
    assert num(acc[biz["sntg"].username]["sales"]["revenue"]) == 9000 - 3000
    assert acc[biz["company"].username]["sales"]["jobs"] == 0
    assert acc[biz["company"].username]["managed"]["jobs"] == 1


def test_date_range_filters_by_delivery_date(client, biz):
    a = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], price=5000)).json()
    deliver(client, biz["hd"], a["id"], date(2026, 9, 15))
    data, acc = _perf(client, biz["hc"], date_from="2026-10-01", date_to="2026-10-31")
    assert acc[biz["diego"].username]["sales"]["jobs"] == 0
    data, acc = _perf(client, biz["hc"], date_from="2026-09-01", date_to="2026-09-30")
    assert acc[biz["diego"].username]["sales"]["jobs"] == 1


def test_company_dashboard_is_the_central_view(client, biz):
    """La Empresa ve el total de sus socios y lo propio, cada venta una vez, la haya
    registrado quien la haya registrado. Ingresos sin delivery, que va aparte."""
    today = date.today()
    a = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], price=20000)).json()  # la registró Diego
    b = client.post("/api/sales", headers=biz["hc"], json=sale_payload(biz["ps"], price=15000)).json()  # la Empresa, de Sntg
    deliver(client, biz["hd"], a["id"], today)
    deliver(client, biz["hc"], b["id"], today)
    params = {"date_from": str(today), "date_to": str(today)}
    s = client.get("/api/dashboard/summary", headers=biz["hc"], params=params).json()
    assert s["total_jobs"] == 2 and num(s["total_revenue"]) == 35000 - 2 * 3000
    assert num(s["total_delivery"]) == 2 * 3000
    assert num(s["total_revenue"]) - num(s["total_cost"]) == num(s["total_profit"])
    # Cada socio sigue viendo solo lo suyo.
    d = client.get("/api/dashboard/summary", headers=biz["hd"], params=params).json()
    assert d["total_jobs"] == 1 and num(d["total_revenue"]) == 20000 - 3000
    month = client.get("/api/history/monthly", headers=biz["hc"]).json()[0]
    assert month["total_jobs"] >= 2


def test_piece_price_is_separate_from_delivery(client, make):
    """El precio puesto a mano es el de la impresión: el delivery se suma al total cobrado."""
    u = make.user()
    h = make.headers(u)
    body = sale_payload(make.printer(u), price=None, piece_price=6000, shipping_cost=2000)
    del body["price"]
    r = client.post("/api/sales", headers=h, json=body)
    assert r.status_code == 201, r.text
    s = r.json()
    assert num(s["price"]) == 8000 and num(s["piece_price"]) == 6000 and num(s["delivery_amount"]) == 2000
    # Editar el precio de la impresión conserva el delivery.
    r = client.put(f"/api/sales/{s['id']}", headers=h, json={"piece_price": 7000})
    assert r.status_code == 200, r.text
    assert num(r.json()["price"]) == 9000 and num(r.json()["piece_price"]) == 7000
    # Una versión vieja de la app sigue mandando el total en "price".
    r = client.post("/api/sales", headers=h, json=sale_payload(make.printer(u), price=9000, shipping_cost=1000))
    assert num(r.json()["price"]) == 9000 and num(r.json()["piece_price"]) == 8000
    # Sin ningún precio no se registra.
    assert client.post("/api/sales", headers=h, json=body | {"piece_price": None}).status_code == 400
    # Un regalo con delivery no lo cobra: el precio de la impresión no baja de $0.
    g = client.post("/api/sales", headers=h, json=sale_payload(make.printer(u), payment_method="cortesia")).json()
    assert num(g["price"]) == 0 and num(g["piece_price"]) == 0
