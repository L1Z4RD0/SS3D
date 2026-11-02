"""Saldo de la Caja (cierre real y retiros), filtro de Ventas por cuenta y dar de baja filamentos."""
from datetime import date, timedelta
from decimal import Decimal

from conftest import deliver, sale_payload
from test_company import _company_filament, biz  # noqa: F401  (biz es un fixture)

from app.config import settings

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")
PREV_MONTH = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def _company_sale(client, biz, price=10000):
    """Venta de la Empresa en la impresora de Sntg con filamento de la Empresa, entregada."""
    fc = _company_filament(client, biz)
    body = sale_payload(biz["ps"], owner_id=biz["company"].id, price=price, client_name="Cliente Empresa")
    body["filaments"] = [{"filament_id": fc["id"], "grams_used": 50}]
    r = client.post("/api/sales", headers=biz["hc"], json=body)
    assert r.status_code == 201, r.text
    return deliver(client, biz["hc"], r.json()["id"], TODAY)


def test_cash_box_opening_withdrawals_and_closing(client, biz, monkeypatch):
    monkeypatch.setattr(settings, "split_partners", f"{biz['diego'].username},{biz['sntg'].username},Omar")
    h = biz["hd"]
    _company_sale(client, biz)
    # Cierre real del mes anterior: es el saldo inicial de este mes.
    r = client.put("/api/beta/cash-box/closing", headers=h,
                   json={"month": PREV_MONTH, "amount": 50000, "note": "Contado en efectivo"})
    assert r.status_code == 200, r.text
    expense = client.post("/api/beta/expenses", headers=h,
                          json={"expense_date": str(TODAY), "concept": "Bolsas", "amount": 1500, "paid_by": "Caja"})
    w = client.post("/api/beta/cash-box/withdrawals", headers=h,
                    json={"withdrawal_date": str(TODAY), "amount": 8000, "concept": "Compra de laca"})
    assert w.status_code == 201, w.text

    box = client.get("/api/beta/cash-box", headers=h, params={"month": MONTH}).json()
    split = client.get("/api/beta/split", headers=h, params={"month": MONTH}).json()
    caja_total = next(Decimal(p["total"]) for p in split["partners"] if p["is_cash_box"])
    assert box["opening_month"] == PREV_MONTH and box["opening_note"] == "Contado en efectivo"
    assert Decimal(box["opening"]) == 50000
    assert Decimal(box["split_income"]) == caja_total
    assert Decimal(box["expenses_paid"]) == 1500 and Decimal(box["withdrawals_total"]) == 8000
    estimated = 50000 + caja_total - 1500 - 8000
    assert Decimal(box["estimated"]) == estimated
    assert box["closing"] is None and box["difference"] is None

    # Cierre real de este mes, con explicación: queda la diferencia contra el estimado.
    r = client.put("/api/beta/cash-box/closing", headers=biz["hc"],
                   json={"month": MONTH, "amount": 40000, "note": "Faltó un vuelto"})
    assert r.status_code == 200 and r.json()["updated_by"] == biz["company"].username
    box = client.get("/api/beta/cash-box", headers=h, params={"month": MONTH}).json()
    assert Decimal(box["closing"]["amount"]) == 40000
    assert Decimal(box["difference"]) == 40000 - estimated
    # Corregirlo reemplaza el anterior (uno por mes).
    client.put("/api/beta/cash-box/closing", headers=h, json={"month": MONTH, "amount": 41000, "note": "Recontado"})
    box = client.get("/api/beta/cash-box", headers=h, params={"month": MONTH}).json()
    assert box["closing"]["note"] == "Recontado"

    # Borrar el retiro sube el estimado.
    assert client.delete(f"/api/beta/cash-box/withdrawals/{w.json()['id']}", headers=h).status_code == 204
    box = client.get("/api/beta/cash-box", headers=h, params={"month": MONTH}).json()
    assert Decimal(box["estimated"]) == estimated + 8000
    assert client.delete("/api/beta/cash-box/closing", headers=h, params={"month": MONTH}).status_code == 204
    # Gastos y cierres son de toda la Empresa: se limpian para no mover el Reparto de otros tests.
    client.delete(f"/api/beta/expenses/{expense.json()['id']}", headers=h)
    client.delete("/api/beta/cash-box/closing", headers=h, params={"month": PREV_MONTH})


def test_cash_box_needs_explanation_and_split_access(client, biz, make):
    r = client.put("/api/beta/cash-box/closing", headers=biz["hc"], json={"month": MONTH, "amount": 1000, "note": ""})
    assert r.status_code == 422
    r = client.post("/api/beta/cash-box/withdrawals", headers=biz["hc"],
                    json={"withdrawal_date": str(TODAY), "amount": 0, "concept": "x"})
    assert r.status_code == 422
    outsider = make.user(name="externo")
    assert client.get("/api/beta/cash-box", headers=make.headers(outsider)).status_code == 403


def test_sales_filter_by_company_account(client, biz):
    company_sale = _company_sale(client, biz)
    # Venta que la Empresa registra a nombre de Diego (con su impresora).
    registered = client.post("/api/sales", headers=biz["hc"],
                             json=sale_payload(biz["pd"], owner_id=biz["diego"].id, client_name="Registrada")).json()
    own_diego = client.post("/api/sales", headers=biz["hd"], json=sale_payload(biz["pd"], client_name="De Diego")).json()

    def ids(account):
        r = client.get("/api/sales", headers=biz["hc"], params={"account_id": str(account.id), "limit": 200})
        assert r.status_code == 200, r.text
        return {s["id"] for s in r.json()["items"]}

    assert ids(biz["company"]) == {company_sale["id"], registered["id"]}
    assert own_diego["id"] in ids(biz["diego"]) and company_sale["id"] not in ids(biz["diego"])
    # El filtro no amplía lo que cada uno puede ver: Diego solo ve, de la Empresa, lo que ella
    # registró a su nombre (no la venta propia de la Empresa).
    r = client.get("/api/sales", headers=biz["hd"], params={"account_id": str(biz["company"].id)})
    assert {s["id"] for s in r.json()["items"]} == {registered["id"]}
    # El Excel respeta el filtro.
    r = client.get("/api/sales/export.xlsx", headers=biz["hc"], params={"account_id": str(biz["company"].id)})
    assert r.status_code == 200


def test_retiring_filaments_keeps_delivered_sales_intact(client, make):
    u = make.user()
    p, h = make.printer(u), make.headers(u)
    used, empty, unused = make.filament(u, grams=100), make.filament(u, grams=100, color="Azul"), make.filament(u)
    sale = client.post("/api/sales", headers=h, json=sale_payload(p, used, grams=100)).json()
    sale = deliver(client, h, sale["id"])
    # Un carrete agotado que nunca se usó en una venta (ej. se acabó sin registrarlo).
    client.put(f"/api/inventory/filaments/{empty.id}", headers=h, json={"available_g": 0})

    before = client.get(f"/api/sales/{sale['id']}", headers=h).json()
    summary_before = client.get("/api/dashboard/summary", headers=h).json()
    r = client.post("/api/inventory/filaments/retire-exhausted", headers=h)
    assert r.status_code == 200, r.text
    listed = {f["id"] for f in client.get("/api/inventory/filaments?include_exhausted=true", headers=h).json()}
    assert str(used.id) not in listed and str(unused.id) in listed

    after = client.get(f"/api/sales/{sale['id']}", headers=h).json()
    for key in ("price", "total_cost", "material_cost", "profit", "status", "filaments_used"):
        assert after[key] == before[key], key
    assert client.get("/api/dashboard/summary", headers=h).json() == summary_before
    # Editar la venta entregada después de darlo de baja sigue funcionando.
    r = client.put(f"/api/sales/{sale['id']}", headers=h, json={"notes": "ok", "payment_method": "transferencia"})
    assert r.status_code == 200, r.text
    assert r.json()["material_cost"] == before["material_cost"]

    # Uno con stock también se puede dar de baja a mano (ej. ya no existe en la realidad).
    assert client.delete(f"/api/inventory/filaments/{unused.id}", headers=h).status_code == 204
    assert client.post("/api/inventory/filaments/retire-exhausted", headers=h).json() == {"retired": 0}
