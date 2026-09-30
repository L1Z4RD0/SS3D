"""Insumos en negativo ("fiados") con costo provisional y corrección al reponer."""
from decimal import Decimal

from conftest import deliver, sale_payload

from app.models.supply import Supply


def _supplies(client, h):
    return {s["id"]: s for s in client.get("/api/inventory/supplies", headers=h).json()}


def _restock(client, h, supply_id, quantity, total_cost):
    r = client.post(f"/api/inventory/supplies/{supply_id}/restock", headers=h,
                    json={"quantity": quantity, "total_cost": total_cost})
    assert r.status_code == 200, r.text
    return r.json()


def _sale(client, h, sale_id):
    return client.get(f"/api/sales/{sale_id}", headers=h).json()


def test_selling_without_stock_goes_negative_with_provisional_cost(client, db, make):
    u = make.user()
    p, s = make.printer(u), make.supply(u, qty=3, unit_cost=100)
    h = make.headers(u)
    r = client.post("/api/sales", headers=h, json=sale_payload(p, supply=s, qty=5))
    assert r.status_code == 201, r.text
    sale = r.json()
    assert sale["has_provisional_costs"] is True
    assert Decimal(sale["supplies_used"][0]["pending_qty"]) == 2  # 3 había, 2 fiadas
    assert Decimal(sale["supplies_cost"]) == 500  # provisional: 5 × $100
    listed = _supplies(client, h)[str(s.id)]
    assert Decimal(listed["quantity_available"]) == -2
    assert Decimal(listed["owed_qty"]) == 2 and Decimal(listed["pending_cost_qty"]) == 2


def test_restock_reprices_owed_units_and_fixes_sale_profit(client, db, make):
    u = make.user()
    p, s = make.printer(u), make.supply(u, qty=3, unit_cost=100)
    h = make.headers(u)
    sale = client.post("/api/sales", headers=h, json=sale_payload(p, supply=s, qty=5)).json()
    sale = deliver(client, h, sale["id"])  # ya entregada: igual se corrige su ganancia

    # Compra real: 10 unidades a $150 c/u (el precio subió).
    res = _restock(client, h, s.id, 10, 1500)
    assert Decimal(res["settled_qty"]) == 2 and res["repriced_sales"] == 1
    assert Decimal(res["cost_adjustment"]) == 100  # 2 unidades × $50 de diferencia
    assert Decimal(res["supply"]["quantity_available"]) == 8  # -2 + 10
    assert Decimal(res["supply"]["owed_qty"]) == 0 and Decimal(res["supply"]["unit_cost"]) == 150

    after = _sale(client, h, sale["id"])
    assert after["has_provisional_costs"] is False
    assert Decimal(after["supplies_cost"]) == 600  # 3 × $100 + 2 × $150
    assert Decimal(after["total_cost"]) == Decimal(sale["total_cost"]) + 100
    assert Decimal(after["profit"]) == Decimal(sale["profit"]) - 100


def test_partial_restock_and_oldest_sale_first(client, make):
    u = make.user()
    p, s = make.printer(u), make.supply(u, qty=0, unit_cost=100)
    h = make.headers(u)
    first = client.post("/api/sales", headers=h, json=sale_payload(p, supply=s, qty=2)).json()
    second = client.post("/api/sales", headers=h, json=sale_payload(p, supply=s, qty=3)).json()

    res = _restock(client, h, s.id, 3, 600)  # $200 c/u: alcanza para 3 de las 5 fiadas
    assert Decimal(res["settled_qty"]) == 3 and res["repriced_sales"] == 2
    assert Decimal(res["supply"]["quantity_available"]) == -2
    a, b = _sale(client, h, first["id"]), _sale(client, h, second["id"])
    assert a["has_provisional_costs"] is False and Decimal(a["supplies_cost"]) == 400
    assert b["has_provisional_costs"] is True
    assert Decimal(b["supplies_used"][0]["pending_qty"]) == 2
    assert Decimal(b["supplies_cost"]) == 400  # 1 a $200 + 2 aún provisionales a $100

    res = _restock(client, h, s.id, 5, 1000)
    assert Decimal(res["settled_qty"]) == 2
    b = _sale(client, h, second["id"])
    assert b["has_provisional_costs"] is False and Decimal(b["supplies_cost"]) == 600
    assert Decimal(res["supply"]["quantity_available"]) == 3


def test_cancelling_or_editing_returns_owed_units(client, db, make):
    u = make.user()
    p, s = make.printer(u), make.supply(u, qty=1, unit_cost=100)
    h = make.headers(u)
    sale = client.post("/api/sales", headers=h, json=sale_payload(p, supply=s, qty=4)).json()
    # Editar bajando la cantidad: se devuelve lo anterior y se recalcula lo fiado.
    r = client.put(f"/api/sales/{sale['id']}", headers=h,
                   json={"supplies": [{"supply_id": str(s.id), "quantity": 2}]})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["supplies_used"][0]["pending_qty"]) == 1
    # Cancelar (Pendiente): todo vuelve y ya no queda deuda.
    r = client.post(f"/api/sales/{sale['id']}/cancel", headers=h, json={})
    assert r.status_code == 200, r.text
    assert r.json()["has_provisional_costs"] is False
    listed = _supplies(client, h)[str(s.id)]
    assert Decimal(listed["quantity_available"]) == 1 and Decimal(listed["pending_cost_qty"]) == 0


def test_restock_without_debt_just_adds_stock(client, db, make):
    u = make.user()
    s = make.supply(u, qty=5, unit_cost=100)
    res = _restock(client, make.headers(u), s.id, 10, 1200)
    assert Decimal(res["settled_qty"]) == 0 and res["repriced_sales"] == 0
    assert Decimal(res["supply"]["quantity_available"]) == 15
    assert Decimal(res["supply"]["unit_cost"]) == 120


def test_restock_is_owner_only(client, make):
    owner, other = make.user(), make.user()
    w = make.user("watcher", "obs")
    make.assign(w, owner)
    s = make.supply(owner)
    body = {"quantity": 1, "total_cost": 100}
    assert client.post(f"/api/inventory/supplies/{s.id}/restock", headers=make.headers(other), json=body).status_code == 404
    assert client.post(f"/api/inventory/supplies/{s.id}/restock", headers=make.headers(w), json=body).status_code == 403
    assert client.post(f"/api/inventory/supplies/{s.id}/restock", headers=make.headers(owner),
                       json={"quantity": 0, "total_cost": 100}).status_code == 422
