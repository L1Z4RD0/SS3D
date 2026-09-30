"""Regalar un pedido: pagar "por cortesía" lo registra con precio $0 y costos completos."""
from datetime import date, timedelta
from decimal import Decimal

from conftest import deliver, sale_payload
from test_warehouse import _piece_for, _sell

from app.models.filament import Filament


def test_gift_sale_has_zero_price_and_full_costs(client, db, make):
    u = make.user()
    p, f, s = make.printer(u), make.filament(u), make.supply(u)
    h = make.headers(u)
    # Aunque la app mandara un precio, la cortesía siempre queda en $0.
    r = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100, s, 2, price=9000, payment_method="cortesia"))
    assert r.status_code == 201, r.text
    sale = r.json()
    assert Decimal(sale["price"]) == 0
    assert Decimal(sale["total_cost"]) > 0
    assert Decimal(sale["profit"]) == -Decimal(sale["total_cost"])
    assert Decimal(sale["margin_percent"]) == 0
    # El material se descuenta igual que en cualquier venta.
    db.expire_all()
    assert db.get(Filament, f.id).available_g == Decimal(900)
    # Entregado: no suma ingresos.
    assert Decimal(deliver(client, h, sale["id"])["price"]) == 0


def test_gift_from_calculator(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u)
    body = {
        "printer_id": str(p.id), "filaments": [{"filament_id": str(f.id), "grams_used": 50}], "print_hours": 1,
        "sale_date": str(date.today()), "client_name": "Regalo cumpleaños", "payment_method": "cortesia",
        "chosen_margin_percent": 999,  # se ignora: un regalo no usa escenarios
        "manual_price": 12000,
    }
    r = client.post("/api/calculator/quote/save-as-sale", headers=make.headers(u), json=body)
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["price"]) == 0
    assert Decimal(r.json()["profit"]) == -Decimal(r.json()["total_cost"])


def test_gift_from_warehouse(client, make):
    u = make.user()
    h = make.headers(u)
    piece, _ = _piece_for(client, h, make.printer(u), make.filament(u))
    r = _sell(client, h, piece["id"], payment_method="cortesia", price=5000)
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["price"]) == 0
    assert Decimal(r.json()["profit"]) == -Decimal(piece["cost"])


def test_switching_to_gift_zeroes_price_and_back(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u)
    h = make.headers(u)
    sale = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100, price=9000)).json()
    r = client.put(f"/api/sales/{sale['id']}", headers=h, json={"payment_method": "cortesia"})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["price"]) == 0 and Decimal(r.json()["profit"]) < 0
    # Deja de ser regalo: se le pone precio de nuevo.
    r = client.put(f"/api/sales/{sale['id']}", headers=h, json={"payment_method": "efectivo", "price": 9000})
    assert Decimal(r.json()["price"]) == 9000


def test_gift_while_in_production_only_touches_price(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u)
    h = make.headers(u)
    sale = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100, price=9000)).json()
    client.post(f"/api/sales/{sale['id']}/status", headers=h, json={"status": "en_produccion"})
    r = client.put(f"/api/sales/{sale['id']}", headers=h, json={"payment_method": "cortesia"})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["price"]) == 0
    assert r.json()["total_cost"] == sale["total_cost"]


def test_old_courtesy_sale_keeps_its_price_when_editing_other_fields(client, db, make):
    """Ventas antiguas con Cortesía y precio > 0: editar notas no les borra el precio."""
    from app.models.sale import Sale

    u = make.user()
    p = make.printer(u)
    h = make.headers(u)
    sale = client.post("/api/sales", headers=h, json=sale_payload(p, price=9000)).json()
    row = db.get(Sale, sale["id"])
    row.payment_method = "cortesia"  # como quedó registrada antes de este cambio
    db.commit()
    r = client.put(f"/api/sales/{sale['id']}", headers=h, json={"notes": "solo una nota"})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["price"]) == 9000
