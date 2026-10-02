"""Cuenta Empresa (inventario propio), costos por dueño, delivery y módulo beta de Reparto."""
from datetime import date
from decimal import Decimal

import pytest
from conftest import deliver, sale_payload

from app.config import settings
from app.models.filament import Filament


@pytest.fixture
def biz(db, make):
    diego, sntg = make.user(name="diego"), make.user(name="sntg")
    company = make.user("watcher", "empresa")
    company.is_company = True
    db.commit()
    make.assign(company, diego)
    make.assign(company, sntg)
    return {
        "diego": diego, "sntg": sntg, "company": company,
        "hd": make.headers(diego), "hs": make.headers(sntg), "hc": make.headers(company),
        "pd": make.printer(diego, name="A1 Diego"), "fd": make.filament(diego, color="Rojo"),
        "ps": make.printer(sntg, name="Ender Sntg"), "fs": make.filament(sntg, color="Azul"),
    }


def _company_filament(client, biz, grams=1000):
    r = client.post("/api/inventory/filaments", headers=biz["hc"], json={
        "brand": "Sunlu", "type": "PLA", "color": "Negro", "entry_date": str(date.today()),
        "initial_stock_g": grams, "min_alert_g": 100, "spool_price": 20000})
    assert r.status_code == 201, r.text
    return r.json()


def test_company_has_its_own_inventory(client, biz):
    fc = _company_filament(client, biz)
    assert fc["owner_id"] == str(biz["company"].id)
    me = client.get("/api/auth/me", headers=biz["hc"]).json()
    assert me["is_company"] is True
    observed = client.get("/api/auth/me/observed-users", headers=biz["hc"]).json()
    assert observed[0]["id"] == str(biz["company"].id) and observed[0]["is_self"] is True
    assert {u["id"] for u in observed} == {str(biz["company"].id), str(biz["diego"].id), str(biz["sntg"].id)}
    # Ve su inventario y el de los socios, pero solo edita el suyo.
    ids = {f["id"] for f in client.get("/api/inventory/filaments", headers=biz["hc"]).json()}
    assert {fc["id"], str(biz["fd"].id), str(biz["fs"].id)} <= ids
    assert client.put(f"/api/inventory/filaments/{fc['id']}", headers=biz["hc"], json={"color": "Gris"}).status_code == 200
    assert client.put(f"/api/inventory/filaments/{biz['fd'].id}", headers=biz["hc"], json={"color": "X"}).status_code == 404


def test_plain_watcher_still_cannot_manage_inventory(client, make):
    w = make.user("watcher", "obs")
    r = client.post("/api/inventory/supplies", headers=make.headers(w),
                    json={"name": "x", "category": "y", "quantity_available": 1})
    assert r.status_code == 403


def test_company_sells_with_partner_printer_and_own_filament(client, db, biz):
    fc = _company_filament(client, biz)
    body = sale_payload(biz["pd"], owner_id=biz["diego"].id, price=15000)
    body["filaments"] = [{"filament_id": fc["id"], "grams_used": 100}]
    r = client.post("/api/sales", headers=biz["hc"], json=body)
    assert r.status_code == 201, r.text
    sale = r.json()
    assert sale["owner_id"] == str(biz["diego"].id)
    owners = {o["username"]: o for o in sale["cost_by_owner"]}
    # Máquina para Diego (dueño de la impresora), material para la Empresa.
    d, c = owners[biz["diego"].username], owners[biz["company"].username]
    assert Decimal(d["machine"]) == Decimal(sale["depreciation_cost"]) + Decimal(sale["energy_cost"])
    assert Decimal(d["material"]) == 0
    assert Decimal(c["material"]) == Decimal(sale["material_cost"]) and Decimal(c["machine"]) == 0
    assert Decimal(sale["shared_cost"]) == Decimal(sale["postprocess_cost"]) + Decimal(sale["shipping_cost"])
    db.expire_all()
    assert db.get(Filament, fc["id"]).available_g == Decimal(900)


def test_mixing_rules(client, biz):
    fc = _company_filament(client, biz)
    # Impresora de Diego + filamento de Sntg: no (los socios no se mezclan entre sí).
    body = sale_payload(biz["pd"], biz["fs"], 50, owner_id=biz["diego"].id)
    assert client.post("/api/sales", headers=biz["hc"], json=body).status_code == 404
    # Diego no puede usar el filamento de la Empresa en su propia venta.
    body = sale_payload(biz["pd"])
    body["filaments"] = [{"filament_id": fc["id"], "grams_used": 50}]
    assert client.post("/api/sales", headers=biz["hd"], json=body).status_code == 404


def test_company_calculator_sale_and_plates_with_own_filament(client, biz):
    fc = _company_filament(client, biz)
    body = {"printer_id": str(biz["ps"].id), "filaments": [{"filament_id": fc["id"], "grams_used": 80}],
            "print_hours": 2, "sale_date": str(date.today()), "client_name": "Llaveros",
            "payment_method": "efectivo", "chosen_margin_percent": 140}
    r = client.post("/api/calculator/quote/save-as-sale", headers=biz["hc"], json=body)
    assert r.status_code == 201, r.text
    sale = r.json()
    plate = {"name": "Base", "printer_id": str(biz["ps"].id), "print_hours": 1,
             "filaments": [{"filament_id": fc["id"], "grams_used": 20}]}
    r = client.post(f"/api/sales/{sale['id']}/plates", headers=biz["hc"], json=plate)
    assert r.status_code == 201, r.text


def test_delivery_is_only_a_record(client, biz):
    sale = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], biz["fd"], 50)).json()
    r = client.put(f"/api/sales/{sale['id']}/delivery", headers=biz["hd"],
                   json={"delivery_by": "Omar", "delivery_amount": 2500})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["delivery_by"], Decimal(d["delivery_amount"])) == ("Omar", Decimal(2500))
    assert (d["price"], d["total_cost"], d["profit"]) == (sale["price"], sale["total_cost"], sale["profit"])
    r = client.put(f"/api/sales/{sale['id']}/delivery", headers=biz["hd"], json={"delivery_by": "", "delivery_amount": 99})
    assert r.json()["delivery_by"] is None and Decimal(r.json()["delivery_amount"]) == 0
    client.post(f"/api/sales/{sale['id']}/cancel", headers=biz["hd"], json={})
    r = client.put(f"/api/sales/{sale['id']}/delivery", headers=biz["hd"], json={"delivery_by": "Omar"})
    assert r.status_code == 409


def test_monthly_split(client, db, make, biz, monkeypatch):
    names = f"{biz['diego'].username},{biz['sntg'].username},Omar"
    monkeypatch.setattr(settings, "split_partners", names)
    D, S = biz["diego"].username, biz["sntg"].username
    fc = _company_filament(client, biz)
    today = date.today()
    month = today.strftime("%Y-%m")

    # 1) Venta propia de Diego, cobrada: se le devuelve todo su costo.
    a = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], biz["fd"], 100, price=20000)).json()
    a = deliver(client, biz["hd"], a["id"], today)
    # 2) Venta de la Empresa en la impresora de Sntg con filamento de la Empresa.
    body = sale_payload(biz["ps"], owner_id=biz["sntg"].id, price=10000)
    body["filaments"] = [{"filament_id": fc["id"], "grams_used": 50}]
    b = client.post("/api/sales", headers=biz["hc"], json=body).json()
    b = deliver(client, biz["hc"], b["id"], today)
    client.put(f"/api/sales/{b['id']}/delivery", headers=biz["hc"], json={"delivery_by": "Omar", "delivery_amount": 2000})
    # 3) Venta por cobrar: no entra (queda como pendiente).
    c = client.post("/api/sales", headers=biz["hd"],
                    json=sale_payload(biz["pd"], price=7000, payment_method="por_cobrar")).json()
    deliver(client, biz["hd"], c["id"], today)
    # 4) Pendiente (no entregada): no aparece.
    client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], price=99999))
    # Gasto de la Empresa pagado por Sntg (se le devuelve) y otro por la Caja.
    for paid_by, amount in ((S, 3000), ("Caja", 1000)):
        r = client.post("/api/beta/expenses", headers=biz["hc"],
                        json={"expense_date": str(today), "concept": "Bolsas", "amount": amount, "paid_by": paid_by})
        assert r.status_code == 201, r.text

    r = client.get("/api/beta/split", headers=biz["hc"], params={"month": month})
    assert r.status_code == 200, r.text
    rep = r.json()
    lines = {l["name"]: l for l in rep["partners"]}
    refund_a = Decimal(a["total_cost"])  # todo de Diego
    refund_b = Decimal(b["depreciation_cost"]) + Decimal(b["energy_cost"])  # máquina de Sntg
    assert Decimal(rep["collected_revenue"]) == 30000
    assert Decimal(lines[D]["cost_refund"]) == refund_a - Decimal(a["postprocess_cost"]) - Decimal(a["shipping_cost"])
    assert Decimal(lines[S]["cost_refund"]) == refund_b
    assert Decimal(rep["company_absorbed_cost"]) == Decimal(b["material_cost"])
    assert Decimal(rep["expenses_total"]) == 4000
    expected_net = Decimal(30000) - Decimal(lines[D]["cost_refund"]) - Decimal(lines[S]["cost_refund"]) - 4000
    assert Decimal(rep["net"]) == expected_net
    assert rep["parts"] == 4
    share = (expected_net / 4).quantize(Decimal("0.01"))
    assert all(Decimal(l["share"]) == share for l in rep["partners"])
    assert Decimal(lines[S]["expense_refund"]) == 3000
    assert Decimal(lines[S]["total"]) == share + Decimal(lines[S]["cost_refund"]) + 3000
    assert Decimal(lines["Caja"]["total"]) == share
    assert Decimal(lines["Omar"]["delivery_refund"]) == 2000 and Decimal(lines["Omar"]["total"]) == share
    assert Decimal(rep["pending_total"]) == 7000 and len(rep["sales"]) == 2
    assert [d["delivery_by"] for d in rep["deliveries"]] == ["Omar"]

    # Borrar un gasto.
    exp = client.get("/api/beta/expenses", headers=biz["hc"], params={"month": month}).json()
    assert client.delete(f"/api/beta/expenses/{exp[0]['id']}", headers=biz["hd"]).status_code == 204


def test_split_access(client, make, biz, monkeypatch):
    monkeypatch.setattr(settings, "split_partners", f"{biz['diego'].username},Omar")
    assert client.get("/api/beta/split", headers=biz["hd"]).status_code == 200
    assert client.get("/api/beta/split", headers=biz["hc"]).status_code == 200
    assert client.get("/api/beta/split", headers=make.headers(make.user(name="otro"))).status_code == 403
    assert client.get("/api/beta/split", headers=biz["hd"], params={"month": "2026-13"}).status_code == 400


def test_investment(client, biz):
    fc = _company_filament(client, biz)
    h = biz["hd"]
    own = deliver(client, h, client.post("/api/sales", headers=h, json=sale_payload(biz["pd"], biz["fd"], 100)).json()["id"])
    body = sale_payload(biz["pd"], owner_id=biz["diego"].id)
    body["filaments"] = [{"filament_id": fc["id"], "grams_used": 100}]
    co = client.post("/api/sales", headers=biz["hc"], json=body).json()
    co = deliver(client, biz["hc"], co["id"])
    inv = client.get("/api/beta/investment", headers=h).json()
    [printer] = inv["printers"]
    assert Decimal(printer["invested"]) == 300000
    machine = lambda s: Decimal(s["depreciation_cost"]) + Decimal(s["energy_cost"])
    assert Decimal(printer["recovered"]) == machine(own) + machine(co)  # su máquina en ambas ventas
    assert Decimal(inv["filaments"]["invested"]) == 10000
    assert Decimal(inv["filaments"]["recovered"]) == Decimal(own["material_cost"])  # solo su filamento
    assert client.get("/api/beta/investment", headers=biz["hc"]).status_code == 403


def test_beta_access(client, make, biz, monkeypatch):
    monkeypatch.setattr(settings, "split_partners", f"{biz['diego'].username},Omar")
    d = client.get("/api/beta/access", headers=biz["hd"]).json()
    assert d == {"split": True, "investment": True, "partners": [biz["diego"].username, "Omar", "Caja"]}
    c = client.get("/api/beta/access", headers=biz["hc"]).json()
    assert (c["split"], c["investment"]) == (True, False)
    o = client.get("/api/beta/access", headers=make.headers(make.user(name="otro"))).json()
    assert (o["split"], o["investment"]) == (False, False)
