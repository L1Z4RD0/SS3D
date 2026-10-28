"""Rendimiento por cuenta (solo Empresa): ingresos a quien registró, costos a quien puso
cada recurso y "todas juntas" sin contar dos veces una venta."""
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


def test_revenue_to_registrant_costs_to_resource_owner(client, biz):
    today = date.today()
    # Diego vende con lo suyo.
    a = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], biz["fd"], 100, price=20000)).json()
    deliver(client, biz["hd"], a["id"], today)
    # La Empresa vende en su nombre con la impresora de Diego y SU filamento.
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

    # Ingresos: cada venta a quien la registró.
    assert num(acc[D]["registered"]["revenue"]) == 20000 and acc[D]["registered"]["jobs"] == 1
    assert num(acc[C]["registered"]["revenue"]) == 15000 and acc[C]["registered"]["jobs"] == 1
    assert acc[S]["registered"]["jobs"] == 0

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
    assert combined["jobs"] == 2 and num(combined["revenue"]) == 35000
    assert combined["mixed_sales"] == 1  # B usó la máquina de Diego
    assert len(data["months"]) == 1
    month = data["months"][0]
    assert month["combined"]["jobs"] == 2
    assert num(month["accounts"][str(biz["diego"].id)]["own_cost"]) == num(acc[D]["own_costs"]["total"])


def test_date_range_filters_by_delivery_date(client, biz):
    a = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], price=5000)).json()
    deliver(client, biz["hd"], a["id"], date(2026, 9, 15))
    data, acc = _perf(client, biz["hc"], date_from="2026-10-01", date_to="2026-10-31")
    assert acc[biz["diego"].username]["registered"]["jobs"] == 0
    data, acc = _perf(client, biz["hc"], date_from="2026-09-01", date_to="2026-09-30")
    assert acc[biz["diego"].username]["registered"]["jobs"] == 1
