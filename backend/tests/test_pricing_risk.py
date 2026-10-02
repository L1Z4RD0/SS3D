"""Fórmula de precio: insumos dentro del margen y riesgo de fallo fuera de él."""
from datetime import date
from decimal import Decimal

from conftest import sale_payload


def _quote(client, h, printer, filament, supply=None, risk=None, **extra):
    body = {"printer_id": str(printer.id), "print_hours": 2, "postprocess_hours": 0.5, "shipping_cost": 3000,
            "filaments": [{"filament_id": str(filament.id), "grams_used": 100}],
            "supplies": [{"supply_id": str(supply.id), "quantity": 4}] if supply else []}
    if risk:
        body["risk_level"] = risk
    body.update(extra)
    r = client.post("/api/calculator/quote", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_supplies_are_in_margin_base_and_risk_is_outside(client, make):
    u = make.user()
    p, f, s = make.printer(u), make.filament(u), make.supply(u, unit_cost=100)
    q = _quote(client, make.headers(u), p, f, s, risk="medio")
    b = {k: Decimal(v) for k, v in q["breakdown"].items()}
    # Base del margen: material + depreciación + energía + insumos.
    assert b["margin_base_cost"] == b["material_cost"] + b["depreciation_cost"] + b["energy_cost"] + b["supplies_cost"]
    assert b["supplies_cost"] == 400
    # Extras sin margen: postprocesado + envío.
    assert b["extras_cost"] == b["postprocess_cost"] + b["shipping_cost"]
    # Riesgo medio = 15 % del costo de producción, y no es parte del costo total.
    assert b["risk_percent"] == 15
    assert b["risk_cost"] == (b["margin_base_cost"] * Decimal("0.15")).quantize(Decimal("0.01"))
    assert b["total_cost"] == b["margin_base_cost"] + b["extras_cost"]
    for sc in q["scenarios"]:
        m = Decimal(sc["margin_percent"]) / 100
        expected = (b["margin_base_cost"] * (1 + m) + b["extras_cost"] + b["risk_cost"]).quantize(Decimal("0.01"))
        assert Decimal(sc["price"]) == expected
        assert Decimal(sc["profit"]) == Decimal(sc["price"]) - b["total_cost"]  # la reserva queda en la ganancia


def test_risk_levels_and_default(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u)
    h = make.headers(u)
    prices = {lvl: Decimal(_quote(client, h, p, f, risk=lvl)["scenarios"][1]["price"]) for lvl in ("bajo", "medio", "alto")}
    base = Decimal(_quote(client, h, p, f, risk="bajo")["breakdown"]["margin_base_cost"])
    assert prices["medio"] - prices["bajo"] == (base * Decimal("0.05")).quantize(Decimal("0.01"))
    assert prices["bajo"] < prices["medio"] < prices["alto"]
    # Sin indicar nivel: riesgo bajo (10 %).
    assert Decimal(_quote(client, h, p, f)["breakdown"]["risk_percent"]) == 10
    r = client.post("/api/calculator/quote", headers=h, json={"printer_id": str(p.id), "risk_level": "extremo"})
    assert r.status_code == 422


def test_risk_includes_extra_plates(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u)
    plate = {"name": "Base", "printer_id": str(p.id), "print_hours": 3,
             "filaments": [{"filament_id": str(f.id), "grams_used": 50}]}
    q = _quote(client, make.headers(u), p, f, risk="alto", extra_plates=[plate])
    b = q["breakdown"]
    assert Decimal(b["risk_cost"]) == (Decimal(b["margin_base_cost"]) * Decimal("0.20")).quantize(Decimal("0.01"))


def test_sale_stores_risk(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u)
    h = make.headers(u)
    sale = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100, risk_level="alto")).json()
    base = Decimal(sale["material_cost"]) + Decimal(sale["depreciation_cost"]) + Decimal(sale["energy_cost"])
    assert Decimal(sale["risk_percent"]) == 20
    assert Decimal(sale["risk_amount"]) == (base * Decimal("0.20")).quantize(Decimal("0.01"))
    # El riesgo no es un costo: la ganancia sigue siendo precio − costo total.
    assert Decimal(sale["profit"]) == Decimal(sale["price"]) - Decimal(sale["total_cost"])

    # Edición completa sin indicar nivel: conserva el que tenía y recalcula el monto.
    r = client.put(f"/api/sales/{sale['id']}", headers=h,
                   json={"filaments": [{"filament_id": str(f.id), "grams_used": 200}]})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["risk_percent"]) == 20
    assert Decimal(r.json()["risk_amount"]) > Decimal(sale["risk_amount"])
    # Cambiar el nivel.
    r = client.put(f"/api/sales/{sale['id']}", headers=h, json={"risk_level": "bajo"})
    assert Decimal(r.json()["risk_percent"]) == 10
    # Pasar a regalo: sin cobro, sin reserva.
    r = client.put(f"/api/sales/{sale['id']}", headers=h, json={"payment_method": "cortesia"})
    assert Decimal(r.json()["price"]) == 0 and Decimal(r.json()["risk_amount"]) == 0


def test_calculator_sale_stores_risk_and_gift_has_none(client, make):
    u = make.user()
    p, f = make.printer(u), make.filament(u)
    h = make.headers(u)
    body = {"printer_id": str(p.id), "filaments": [{"filament_id": str(f.id), "grams_used": 100}], "print_hours": 2,
            "risk_level": "medio", "sale_date": str(date.today()), "client_name": "Figura",
            "payment_method": "efectivo", "chosen_margin_percent": 140}
    sale = client.post("/api/calculator/quote/save-as-sale", headers=h, json=body).json()
    q = _quote(client, h, p, f, risk="medio", postprocess_hours=0, shipping_cost=0)
    assert Decimal(sale["risk_percent"]) == 15
    assert Decimal(sale["price"]) == Decimal(q["scenarios"][1]["price"])
    gift = client.post("/api/calculator/quote/save-as-sale", headers=h, json={**body, "payment_method": "cortesia"}).json()
    assert Decimal(gift["price"]) == 0 and Decimal(gift["risk_amount"]) == 0
