"""Cancelar con la pieza dañada a medio imprimir (% impreso, horas usadas y postprocesado),
corregir esa pérdida en el mes, y que el Reparto la devuelva a cada dueño de recurso."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from conftest import deliver, sale_payload

from app.config import settings
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import Sale
from app.models.supply import Supply
from app.models.user import User
from app.models.warehouse_item import WarehouseItem
from app.services.calculator import money

TODAY = date.today()


@pytest.fixture
def setup(client, make):
    """Pedido de 100 g (de 1000), 2 argollas (de 50), 2 h de impresión, 0,5 h de postprocesado."""
    u = make.user()
    p, f, s = make.printer(u), make.filament(u), make.supply(u)
    h = make.headers(u)
    sale = client.post("/api/sales", headers=h, json=sale_payload(p, f, 100, s, 2, price=9000)).json()
    return {"u": u, "h": h, "sale": sale, "p": p, "f": f, "s": s}


def _to(client, setup, *statuses):
    for st in statuses:
        r = client.post(f"/api/sales/{setup['sale']['id']}/status", headers=setup["h"], json={"status": st})
        assert r.status_code == 200, r.text


def _cancel(client, setup, **body):
    return client.post(f"/api/sales/{setup['sale']['id']}/cancel", headers=setup["h"], json=body)


def _stock(db, setup):
    db.expire_all()
    return (db.get(Filament, setup["f"].id).available_g, db.get(Supply, setup["s"].id).quantity_available,
            db.get(Printer, setup["p"].id).hours_used)


def _costs(sale):
    return {k: Decimal(sale[k]) for k in ("material_cost", "depreciation_cost", "energy_cost", "postprocess_cost",
                                         "supplies_cost")}


def test_partial_print_returns_the_rest_and_charges_only_what_was_used(client, db, setup):
    _to(client, setup, "en_produccion")
    c = _costs(setup["sale"])
    r = _cancel(client, setup, piece_outcome="inutilizable", printed_percent=25)
    assert r.status_code == 200, r.text
    data = r.json()
    # 25 g usados (75 vuelven), 0,5 h usadas (1,5 vuelven), insumos devueltos (En producción).
    assert _stock(db, setup) == (Decimal(975), Decimal(50), Decimal("0.5"))
    expected = money(c["material_cost"] * Decimal("0.25") + (c["depreciation_cost"] + c["energy_cost"]) * Decimal("0.25"))
    assert Decimal(data["loss_amount"]) == expected  # sin postprocesado (por defecto: no)
    assert Decimal(data["cancel_printed_percent"]) == 25 and Decimal(data["cancel_print_hours"]) == Decimal("0.5")
    assert data["cancel_postprocess_done"] is False and data["loss_editable"] is True


def test_custom_hours_and_postprocess(client, db, setup):
    _to(client, setup, "en_produccion")
    c = _costs(setup["sale"])
    r = _cancel(client, setup, piece_outcome="inutilizable", printed_percent=50, print_hours_used=1.5,
                postprocess_done=True)
    assert r.status_code == 200, r.text
    assert _stock(db, setup)[2] == Decimal("1.5")
    machine = (c["depreciation_cost"] + c["energy_cost"]) * Decimal("0.75")
    expected = money(c["material_cost"] / 2 + machine + c["postprocess_cost"])
    assert Decimal(r.json()["loss_amount"]) == expected


def test_hours_cannot_exceed_planned(client, setup):
    _to(client, setup, "en_produccion")
    r = _cancel(client, setup, piece_outcome="inutilizable", printed_percent=50, print_hours_used=5)
    assert r.status_code == 400


def test_ready_discard_keeps_supplies_consumed_and_shows_loss(client, db, setup):
    _to(client, setup, "en_produccion", "lista")
    c = _costs(setup["sale"])
    r = _cancel(client, setup, piece_outcome="descartar", discard_reason="danada", printed_percent=100)
    assert r.status_code == 200, r.text
    assert _stock(db, setup) == (Decimal(900), Decimal(48), Decimal(2))
    assert Decimal(r.json()["loss_amount"]) == money(
        c["material_cost"] + c["depreciation_cost"] + c["energy_cost"] + c["supplies_cost"])
    # La pérdida aparece en la hoja de Ventas (antes quedaba en una pieza "Descartada").
    listed = client.get("/api/sales", headers=setup["h"], params={"status": "cancelado"}).json()["items"]
    assert Decimal(next(s for s in listed if s["id"] == setup["sale"]["id"])["loss_amount"]) > 0


def test_edit_loss_in_same_month_adjusts_stock(client, db, setup):
    _to(client, setup, "en_produccion")
    _cancel(client, setup, piece_outcome="inutilizable", printed_percent=25)
    r = client.put(f"/api/sales/{setup['sale']['id']}/cancellation-loss", headers=setup["h"],
                   json={"printed_percent": 50, "postprocess_done": False})
    assert r.status_code == 200, r.text
    assert _stock(db, setup) == (Decimal(950), Decimal(50), Decimal(1))  # 50 g y 1 h consumidos
    assert Decimal(r.json()["cancel_printed_percent"]) == 50
    assert "Pérdida corregida" in r.json()["status_history"][-1]["note"]


def test_edit_loss_not_allowed_after_the_month(client, db, setup):
    _to(client, setup, "en_produccion")
    _cancel(client, setup, piece_outcome="inutilizable", printed_percent=25)
    sale = db.get(Sale, setup["sale"]["id"])
    sale.cancelled_at = datetime.now(timezone.utc) - timedelta(days=40)
    db.commit()
    r = client.put(f"/api/sales/{setup['sale']['id']}/cancellation-loss", headers=setup["h"],
                   json={"printed_percent": 50})
    assert r.status_code == 409


def test_old_discarded_piece_shows_loss_and_can_be_corrected(client, db, setup):
    """Cancelado antes de esta función (ej. los Renos del 2 de noviembre): la pérdida estaba en
    una pieza "Descartada". Se muestra en el pedido y al corregirla pasa al pedido."""
    _to(client, setup, "en_produccion", "lista")
    _cancel(client, setup, piece_outcome="descartar", discard_reason="danada", printed_percent=100)
    sale = db.get(Sale, setup["sale"]["id"])
    loss = sale.loss_amount
    # Simula el registro antiguo: pérdida en una pieza descartada, no en el pedido.
    sale.loss_amount = 0
    sale.cancel_printed_percent = sale.cancel_print_hours = sale.cancel_postprocess_done = None
    db.add(WarehouseItem(user_id=sale.user_id, origin_sale_id=sale.id, name=sale.client_name, entry_date=TODAY,
                         cost=loss, price=sale.total_price, status="descartada", discard_reason="danada",
                         discarded_at=sale.cancelled_at))
    db.commit()
    shown = client.get(f"/api/sales/{sale.id}", headers=setup["h"]).json()
    assert Decimal(shown["loss_amount"]) == loss and shown["loss_editable"] is True

    r = client.put(f"/api/sales/{sale.id}/cancellation-loss", headers=setup["h"], json={"printed_percent": 50})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(WarehouseItem).filter(WarehouseItem.origin_sale_id == sale.id).count() == 0
    assert _stock(db, setup)[0] == Decimal(950)  # la mitad del filamento vuelve
    assert Decimal(r.json()["loss_amount"]) < loss


def test_delete_partial_cancel_returns_only_what_was_consumed(client, db, setup):
    _to(client, setup, "en_produccion")
    _cancel(client, setup, piece_outcome="inutilizable", printed_percent=25)
    assert client.delete(f"/api/sales/{setup['sale']['id']}", headers=setup["h"]).status_code == 204
    assert _stock(db, setup) == (Decimal(1000), Decimal(50), Decimal(0))


# ---------------------------------------------------------------------------
# Reparto
# ---------------------------------------------------------------------------


@pytest.fixture
def biz(db, make, monkeypatch):
    diego, sntg = make.user(name="diego"), make.user(name="sntg")
    db.query(User).filter(User.is_company.is_(True)).update({User.is_company: False})
    company = make.user("watcher", "empresa")
    company.is_company = True
    db.commit()
    make.assign(company, diego)
    make.assign(company, sntg)
    monkeypatch.setattr(settings, "split_partners", f"{diego.username},{sntg.username},Omar")
    return {"diego": diego, "sntg": sntg, "company": company, "hc": make.headers(company),
            "pd": make.printer(diego), "fc": make.filament(company, color="Negro")}


def _company_sale(client, biz, price=12000):
    body = sale_payload(biz["pd"], biz["fc"], 100, price=price, owner_id=biz["company"].id)
    s = client.post("/api/sales", headers=biz["hc"], json=body)
    assert s.status_code == 201, s.text
    return s.json()


def _split(client, biz, month=None):
    r = client.get("/api/beta/split", headers=biz["hc"], params={"month": month or TODAY.strftime("%Y-%m")})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.skipif(TODAY < date(2026, 11, 1), reason="las pérdidas entran al Reparto desde noviembre 2026")
def test_split_returns_losses_to_each_owner_and_lowers_net(client, db, biz):
    before = _split(client, biz)
    s = _company_sale(client, biz)
    client.post(f"/api/sales/{s['id']}/status", headers=biz["hc"], json={"status": "en_produccion"})
    r = client.post(f"/api/sales/{s['id']}/cancel", headers=biz["hc"],
                    json={"piece_outcome": "inutilizable", "printed_percent": 50, "reason": "Se despegó"})
    assert r.status_code == 200, r.text
    after = _split(client, biz)

    line = next(l for l in after["losses"] if l["id"] == s["id"])
    assert line["kind"] == "cancelado" and line["status_before"] == "En producción"
    assert Decimal(line["printed_percent"]) == 50 and "Se despegó" in line["reason"]
    owners = {o["name"]: o for o in line["owners"]}
    # Máquina al dueño de la impresora (Diego); el filamento de la Empresa, a la Caja.
    assert Decimal(owners[biz["diego"].username]["machine"]) > 0
    assert Decimal(owners["Caja"]["material"]) > 0
    assert Decimal(line["total"]) == Decimal(r.json()["loss_amount"])

    added = Decimal(after["losses_total"]) - Decimal(before["losses_total"])
    assert added == Decimal(line["total"])
    assert Decimal(before["net"]) - Decimal(after["net"]) == added
    partners = {p["name"]: p for p in after["partners"]}
    assert Decimal(partners[biz["diego"].username]["loss_refund"]) >= Decimal(owners[biz["diego"].username]["total"])


def test_split_ignores_losses_before_november_2026(client, db, biz):
    s = _company_sale(client, biz)
    client.post(f"/api/sales/{s['id']}/status", headers=biz["hc"], json={"status": "en_produccion"})
    client.post(f"/api/sales/{s['id']}/cancel", headers=biz["hc"], json={"piece_outcome": "inutilizable",
                                                                       "printed_percent": 100})
    sale = db.get(Sale, s["id"])
    sale.cancelled_at = datetime(2026, 10, 20, 15, tzinfo=timezone.utc)
    db.commit()
    assert _split(client, biz, "2026-10")["losses"] == []


@pytest.mark.skipif(TODAY < date(2026, 11, 1), reason="las pérdidas entran al Reparto desde noviembre 2026")
def test_piece_discarded_from_warehouse_is_a_loss_of_that_month(client, db, biz):
    s = _company_sale(client, biz)
    client.post(f"/api/sales/{s['id']}/status", headers=biz["hc"], json={"status": "en_produccion"})
    piece = client.post(f"/api/sales/{s['id']}/cancel", headers=biz["hc"],
                        json={"keep_hours": True, "piece_outcome": "almacen"}).json()["warehouse_piece"]
    # En el Almacén es un activo: todavía no es pérdida.
    assert all(l["id"] != s["id"] for l in _split(client, biz)["losses"])
    item = db.get(WarehouseItem, piece["id"])
    item.status, item.discard_reason, item.discarded_at = "descartada", "danada", datetime.now(timezone.utc) + timedelta(hours=2)
    db.commit()
    line = next(l for l in _split(client, biz)["losses"] if l["id"] == s["id"])
    assert line["kind"] == "descartada_almacen" and Decimal(line["total"]) == Decimal(piece["cost"])


def test_warehouse_sale_splits_cost_by_resource_owner(client, db, biz):
    """Vender una pieza del Almacén: su costo se reparte como el consumo del pedido original
    (máquina al dueño de la impresora, filamento de la Empresa a la Empresa)."""
    s = _company_sale(client, biz)
    client.post(f"/api/sales/{s['id']}/status", headers=biz["hc"], json={"status": "en_produccion"})
    piece = client.post(f"/api/sales/{s['id']}/cancel", headers=biz["hc"],
                        json={"keep_hours": True, "piece_outcome": "almacen"}).json()["warehouse_piece"]
    sold = client.post(f"/api/warehouse/{piece['id']}/sell", headers=biz["hc"],
                       json={"promised_delivery_date": str(TODAY), "payment_method": "efectivo"})
    assert sold.status_code in (200, 201), sold.text
    owners = {o["username"]: o for o in sold.json()["cost_by_owner"]}
    assert Decimal(owners[biz["diego"].username]["machine"]) > 0
    assert Decimal(owners[biz["company"].username]["material"]) > 0
    assert sum(Decimal(o["total"]) for o in owners.values()) == Decimal(piece["cost"])
