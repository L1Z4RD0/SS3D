"""Cuenta Empresa (inventario propio), costos por dueño, delivery y módulo beta de Reparto."""
from datetime import date
from decimal import Decimal

import pytest
from conftest import deliver, sale_payload

from app.config import settings
from app.models.filament import Filament


@pytest.fixture
def biz(db, make):
    from app.models.user import User

    diego, sntg = make.user(name="diego"), make.user(name="sntg")
    # En producción hay una sola cuenta Empresa: las de otros tests no deben entrar en el
    # Reparto de este (sumaría sus ventas a los totales).
    db.query(User).filter(User.is_company.is_(True)).update({User.is_company: False})
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
    assert Decimal(sale["shared_cost"]) == Decimal(sale["postprocess_cost"])  # el delivery no es "común"
    db.expire_all()
    assert db.get(Filament, fc["id"]).available_g == Decimal(900)


def test_company_mixes_materials_of_both_partners(client, db, make, biz, monkeypatch):
    """La Empresa combina materiales de Diego y Sntg: se descuenta a cada dueño y cada costo
    queda a cuenta de quien puso el recurso."""
    from app.models.supply import Supply

    monkeypatch.setattr(settings, "split_partners", f"{biz['diego'].username},{biz['sntg'].username},Omar")
    D, S = biz["diego"].username, biz["sntg"].username
    sd = make.supply(biz["diego"], qty=50, unit_cost=100)
    # Impresora de Diego + filamento de Sntg + insumos de Diego.
    body = sale_payload(biz["pd"], biz["fs"], 120, supply=sd, qty=4, owner_id=biz["diego"].id, price=20000, shipping_cost=0)
    r = client.post("/api/sales", headers=biz["hc"], json=body)
    assert r.status_code == 201, r.text
    sale = r.json()
    owners = {o["username"]: o for o in sale["cost_by_owner"]}
    assert set(owners) == {D, S}
    assert Decimal(owners[D]["machine"]) == Decimal(sale["depreciation_cost"]) + Decimal(sale["energy_cost"])
    assert Decimal(owners[D]["supplies"]) == 400 and Decimal(owners[D]["material"]) == 0
    assert Decimal(owners[S]["material"]) == Decimal(sale["material_cost"]) and Decimal(owners[S]["machine"]) == 0
    # El stock se descuenta a cada dueño.
    db.expire_all()
    assert db.get(Filament, biz["fs"].id).available_g == Decimal(880)
    assert db.get(Supply, sd.id).quantity_available == Decimal(46)
    # En el Reparto, a cada uno se le devuelve lo suyo.
    deliver(client, biz["hc"], sale["id"], date.today())
    rep = client.get("/api/beta/split", headers=biz["hc"], params={"month": date.today().strftime("%Y-%m")}).json()
    [line] = [x for x in rep["sales"] if x["id"] == sale["id"]]
    assert Decimal(line["refunds"][S]) == Decimal(owners[S]["total"])
    assert Decimal(line["refunds"][D]) == Decimal(owners[D]["total"])

    # Una plancha en la impresora de Sntg dentro de esa venta de Diego también se permite.
    other = client.post("/api/sales", headers=biz["hc"], json={**body, "extra_plates": [
        {"name": "Base", "printer_id": str(biz["ps"].id), "print_hours": 1,
         "filaments": [{"filament_id": str(biz["fd"].id), "grams_used": 10}]}]})
    assert other.status_code == 201, other.text
    names = {o["username"] for o in other.json()["cost_by_owner"]}
    assert names == {D, S}


def test_mixing_rules(client, make, biz):
    fc = _company_filament(client, biz)
    # Los socios siguen sin mezclar: Diego no usa filamento de Sntg ni de la Empresa.
    assert client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], biz["fs"], 50)).status_code == 404
    body = sale_payload(biz["pd"])
    body["filaments"] = [{"filament_id": fc["id"], "grams_used": 50}]
    assert client.post("/api/sales", headers=biz["hd"], json=body).status_code == 404
    # La Empresa solo combina lo de los socios que observa: no lo de otro usuario.
    stranger = make.user(name="ajeno")
    foreign = make.filament(stranger)
    body = sale_payload(biz["pd"], foreign, 50, owner_id=biz["diego"].id)
    assert client.post("/api/sales", headers=biz["hc"], json=body).status_code == 404


def test_company_calculator_mixes_partners(client, biz):
    body = {"printer_id": str(biz["pd"].id), "filaments": [{"filament_id": str(biz["fs"].id), "grams_used": 80}],
            "print_hours": 2, "sale_date": str(date.today()), "client_name": "Mixto",
            "payment_method": "efectivo", "chosen_margin_percent": 140}
    r = client.post("/api/calculator/quote/save-as-sale", headers=biz["hc"], json=body)
    assert r.status_code == 201, r.text
    assert {o["username"] for o in r.json()["cost_by_owner"]} == {biz["diego"].username, biz["sntg"].username}
    # Un socio no puede guardar así.
    assert client.post("/api/calculator/quote/save-as-sale", headers=biz["hd"], json=body).status_code in (400, 404)


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


def test_delivery_is_the_sale_shipping_and_keeps_profit(client, biz):
    """El delivery es el monto que paga el cliente por el envío (el campo Delivery de la venta).
    Cambiarlo desde la ventana de estado sube o baja el precio, nunca la ganancia."""
    body = sale_payload(biz["pd"], biz["fd"], 50, price=9000, shipping_cost=0)
    sale = client.post("/api/sales", headers=biz["hd"], json=body).json()
    r = client.put(f"/api/sales/{sale['id']}/delivery", headers=biz["hd"],
                   json={"delivery_by": "Omar", "delivery_amount": 2500})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["delivery_by"], Decimal(d["delivery_amount"])) == ("Omar", Decimal(2500))
    assert Decimal(d["shipping_cost"]) == 2500
    assert Decimal(d["price"]) == Decimal(sale["price"]) + 2500
    assert Decimal(d["total_cost"]) == Decimal(sale["total_cost"]) + 2500
    assert Decimal(d["profit"]) == Decimal(sale["profit"])
    # Quitarlo deja el pedido como estaba.
    r = client.put(f"/api/sales/{sale['id']}/delivery", headers=biz["hd"], json={"delivery_by": "", "delivery_amount": 99})
    d = r.json()
    assert d["delivery_by"] is None and Decimal(d["shipping_cost"]) == 0
    assert (d["price"], d["total_cost"], d["profit"]) == (sale["price"], sale["total_cost"], sale["profit"])
    # Quién lo lleva también se puede indicar al crear o editar la venta.
    other = client.post("/api/sales", headers=biz["hd"], json={**body, "shipping_cost": 2000, "delivery_by": " Sntg "}).json()
    assert other["delivery_by"] == "Sntg" and Decimal(other["delivery_amount"]) == 2000
    r = client.put(f"/api/sales/{other['id']}", headers=biz["hd"], json={"delivery_by": None})
    assert r.json()["delivery_by"] is None
    # Cancelado: no lleva delivery.
    client.post(f"/api/sales/{sale['id']}/cancel", headers=biz["hd"], json={})
    r = client.put(f"/api/sales/{sale['id']}/delivery", headers=biz["hd"], json={"delivery_by": "Omar"})
    assert r.status_code == 409


def test_gift_delivery_is_absorbed_by_profit(client, biz):
    body = sale_payload(biz["pd"], biz["fd"], 50, payment_method="cortesia", shipping_cost=0)
    sale = client.post("/api/sales", headers=biz["hd"], json=body).json()
    d = client.put(f"/api/sales/{sale['id']}/delivery", headers=biz["hd"],
                   json={"delivery_by": "Omar", "delivery_amount": 2000}).json()
    assert Decimal(d["price"]) == 0
    assert Decimal(d["profit"]) == Decimal(sale["profit"]) - 2000


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
    deliver(client, biz["hc"], b["id"], today)
    # Lo llevó Omar y el cliente pagó $2.000 de delivery (reemplaza los $3.000 de la venta).
    b = client.put(f"/api/sales/{b['id']}/delivery", headers=biz["hc"],
                   json={"delivery_by": "Omar", "delivery_amount": 2000}).json()
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
    assert Decimal(rep["collected_revenue"]) == Decimal(a["price"]) + Decimal(b["price"])
    assert Decimal(lines[D]["cost_refund"]) == refund_a - Decimal(a["postprocess_cost"]) - Decimal(a["shipping_cost"])
    assert Decimal(lines[S]["cost_refund"]) == refund_b
    assert Decimal(rep["company_absorbed_cost"]) == Decimal(b["material_cost"])
    assert Decimal(rep["expenses_total"]) == 4000
    # La venta A cobró $3.000 de delivery sin nadie asignado; la B, $2.000 que llevó Omar.
    assert Decimal(rep["deliveries_total"]) == 5000 and Decimal(rep["unassigned_delivery"]) == 3000
    expected_net = (Decimal(a["price"]) + Decimal(b["price"]) - Decimal(lines[D]["cost_refund"])
                    - Decimal(lines[S]["cost_refund"]) - 5000 - 4000)
    assert Decimal(rep["net"]) == expected_net
    assert rep["parts"] == 4
    share = (expected_net / 4).quantize(Decimal("0.01"))
    assert all(Decimal(l["share"]) == share for l in rep["partners"])
    assert Decimal(lines[S]["expense_refund"]) == 3000
    assert Decimal(lines[S]["total"]) == share + Decimal(lines[S]["cost_refund"]) + 3000
    assert Decimal(lines["Caja"]["total"]) == share
    assert Decimal(lines["Omar"]["delivery_refund"]) == 2000 and Decimal(lines["Omar"]["total"]) == share + 2000
    assert Decimal(rep["pending_total"]) == Decimal(c["price"]) and len(rep["sales"]) == 2
    assert sorted(str(d["delivery_by"]) for d in rep["deliveries"]) == ["None", "Omar"]

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


def test_gift_stays_out_of_the_split(client, biz, monkeypatch):
    """Un regalo no reparte costos: lo absorbe quien regaló (antes se le devolvía a Diego y
    se le restaba a todos)."""
    monkeypatch.setattr(settings, "split_partners", f"{biz['diego'].username},{biz['sntg'].username},Omar")
    D = biz["diego"].username
    today = date.today()
    month = today.strftime("%Y-%m")
    h = biz["hd"]

    sale = client.post("/api/sales", headers=h, json=sale_payload(biz["pd"], biz["fd"], 100, price=20000, shipping_cost=0)).json()
    sale = deliver(client, h, sale["id"], today)
    before = client.get("/api/beta/split", headers=h, params={"month": month}).json()

    gift = client.post("/api/sales", headers=h, json=sale_payload(
        biz["pd"], biz["fd"], 100, payment_method="cortesia", shipping_cost=0)).json()
    gift = deliver(client, h, gift["id"], today)
    after = client.get("/api/beta/split", headers=h, params={"month": month}).json()

    # El reparto es exactamente el mismo que sin el regalo.
    for key in ("collected_revenue", "partner_cost_refunds", "net"):
        assert after[key] == before[key], key
    assert [p["total"] for p in after["partners"]] == [p["total"] for p in before["partners"]]
    # El regalo aparece aparte, con su costo a cuenta de Diego.
    [g] = after["gifts"]
    assert g["client_name"] == gift["client_name"]
    assert Decimal(g["cost"]) == Decimal(gift["total_cost"]) == Decimal(after["gifts_cost"])
    assert set(g["absorbed_by"]) == {D}
    sale_ids = {s["id"] for s in after["sales"]}
    assert sale["id"] in sale_ids and gift["id"] not in sale_ids

    # Tampoco cuenta como inversión recuperada.
    inv = client.get("/api/beta/investment", headers=h).json()
    machine = Decimal(sale["depreciation_cost"]) + Decimal(sale["energy_cost"])
    assert Decimal(inv["printers"][0]["recovered"]) == machine
    assert Decimal(inv["filaments"]["recovered"]) == Decimal(sale["material_cost"])


# ---------------------------------------------------------------------------
# La Empresa no tiene impresora: usa la de un socio y la venta queda a su nombre
# ---------------------------------------------------------------------------


def _machine_by_owner(sale):
    """Dueños a los que se les carga máquina (depreciación + luz)."""
    return {o["username"]: Decimal(o["machine"]) for o in sale["cost_by_owner"] if Decimal(o["machine"]) > 0}


def test_company_sale_in_own_name_with_partner_printer(client, db, biz):
    from app.models.printer import Printer

    body = sale_payload(biz["pd"], biz["fs"], 100, owner_id=biz["company"].id, price=15000)
    r = client.post("/api/sales", headers=biz["hc"], json=body)
    assert r.status_code == 201, r.text
    sale = r.json()
    assert sale["owner_id"] == str(biz["company"].id)  # la venta queda en la Empresa
    owners = {o["username"]: o for o in sale["cost_by_owner"]}
    # Depreciación + luz al dueño de la impresora (Diego); el filamento al suyo (Sntg).
    assert Decimal(owners[biz["diego"].username]["machine"]) == Decimal(sale["depreciation_cost"]) + Decimal(sale["energy_cost"])
    assert Decimal(owners[biz["sntg"].username]["material"]) == Decimal(sale["material_cost"])
    assert biz["company"].username not in owners  # la Empresa no puso nada
    db.expire_all()
    assert db.get(Printer, biz["pd"].id).hours_used == Decimal(2)  # las horas van a la impresora de Diego
    assert db.get(Filament, biz["fs"].id).available_g == Decimal(900)


def test_company_can_switch_to_the_other_partner_printer(client, db, biz):
    from app.models.printer import Printer

    sale = client.post("/api/sales", headers=biz["hc"],
                       json=sale_payload(biz["pd"], owner_id=biz["company"].id)).json()
    r = client.put(f"/api/sales/{sale['id']}", headers=biz["hc"], json={"printer_id": str(biz["ps"].id)})
    assert r.status_code == 200, r.text
    assert r.json()["printer_name"] == "Ender Sntg"
    assert set(_machine_by_owner(r.json())) == {biz["sntg"].username}
    db.expire_all()
    assert db.get(Printer, biz["pd"].id).hours_used == 0 and db.get(Printer, biz["ps"].id).hours_used == Decimal(2)


def test_partner_cannot_use_another_partners_printer(client, biz):
    r = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["ps"]))
    assert r.status_code == 404


def test_plain_watcher_still_sells_only_with_the_owner_printer(client, make, biz):
    w = make.user("watcher", "obs")
    make.assign(w, biz["diego"])
    make.assign(w, biz["sntg"])
    r = client.post("/api/sales", headers=make.headers(w), json=sale_payload(biz["ps"], owner_id=biz["diego"].id))
    assert r.status_code == 404


def test_calculator_company_sale_defaults_to_company_with_partner_printer(client, biz):
    body = {"printer_id": str(biz["pd"].id), "filaments": [{"filament_id": str(biz["fs"].id), "grams_used": 50}],
            "print_hours": 1, "postprocess_hours": 0, "shipping_cost": 0, "supplies": [],
            "sale_date": str(date.today()), "client_name": "X", "payment_method": "efectivo",
            "chosen_margin_percent": 140}
    r = client.post("/api/calculator/quote/save-as-sale", headers=biz["hc"], json=body)
    assert r.status_code == 201, r.text
    sale = r.json()
    assert sale["owner_id"] == str(biz["company"].id)
    assert set(_machine_by_owner(sale)) == {biz["diego"].username}
    # Un socio desde la Calculadora sigue vendiendo solo lo suyo (la venta es del dueño de la impresora).
    r = client.post("/api/calculator/quote/save-as-sale", headers=biz["hd"],
                    json={**body, "filaments": [{"filament_id": str(biz["fd"].id), "grams_used": 50}]})
    assert r.status_code == 201 and r.json()["owner_id"] == str(biz["diego"].id)


def test_printer_owner_recovers_investment_from_company_sales(client, biz):
    sale = client.post("/api/sales", headers=biz["hc"],
                       json=sale_payload(biz["pd"], owner_id=biz["company"].id, price=15000)).json()
    deliver(client, biz["hc"], sale["id"])
    inv = client.get("/api/beta/investment", headers=biz["hd"]).json()
    recovered = {p["name"]: Decimal(p["recovered"]) for p in inv["printers"]}
    assert recovered["A1 Diego"] == Decimal(sale["depreciation_cost"]) + Decimal(sale["energy_cost"])
