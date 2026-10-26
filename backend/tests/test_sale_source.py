"""Fuente de venta (Instagram, Facebook, Personal), su gráfico y el orden de la hoja de ventas."""
from datetime import date, timedelta

from conftest import deliver, sale_payload

TODAY = date.today()


def _create(client, h, p, **extra):
    r = client.post("/api/sales", headers=h, json=sale_payload(p, **extra))
    assert r.status_code == 201, r.text
    return r.json()


def _list(client, h, **params):
    r = client.get("/api/sales", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_sale_source_is_saved_and_optional(client, make):
    u = make.user()
    p, h = make.printer(u), make.headers(u)
    assert _create(client, h, p, sale_source="instagram")["sale_source"] == "instagram"
    # Sin fuente (como las ventas anteriores) sigue funcionando.
    assert _create(client, h, p)["sale_source"] is None


def test_unknown_sale_source_is_rejected(client, make):
    u = make.user()
    p = make.printer(u)
    r = client.post("/api/sales", headers=make.headers(u), json=sale_payload(p, sale_source="tiktok"))
    assert r.status_code == 422


def test_sale_source_editable_in_production_and_clearable(client, make):
    u = make.user()
    p, h = make.printer(u), make.headers(u)
    s = _create(client, h, p)
    client.post(f"/api/sales/{s['id']}/status", headers=h, json={"status": "en_produccion"})
    r = client.put(f"/api/sales/{s['id']}", headers=h, json={"sale_source": "facebook"})
    assert r.status_code == 200, r.text
    assert r.json()["sale_source"] == "facebook"
    r = client.put(f"/api/sales/{s['id']}", headers=h, json={"sale_source": None})
    assert r.status_code == 200 and r.json()["sale_source"] is None


def test_filter_by_source_and_unregistered(client, make):
    u = make.user()
    p, h = make.printer(u), make.headers(u)
    ig = _create(client, h, p, sale_source="instagram")
    old = _create(client, h, p)
    assert [s["id"] for s in _list(client, h, sale_source="instagram")["items"]] == [ig["id"]]
    assert [s["id"] for s in _list(client, h, sale_source="sin_registrar")["items"]] == [old["id"]]


def test_calculator_and_warehouse_keep_source(client, make):
    u = make.user()
    p, f, h = make.printer(u), make.filament(u), make.headers(u)
    body = {"printer_id": str(p.id), "filaments": [{"filament_id": str(f.id), "grams_used": 100}],
            "print_hours": 2, "postprocess_hours": 0, "shipping_cost": 0, "supplies": [],
            "sale_date": str(TODAY), "client_name": "X", "payment_method": "efectivo",
            "chosen_margin_percent": 140, "sale_source": "personal"}
    r = client.post("/api/calculator/quote/save-as-sale", headers=h, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["sale_source"] == "personal"

    # Pieza al Almacén y venta de esa pieza con fuente.
    s = _create(client, h, p)
    client.post(f"/api/sales/{s['id']}/status", headers=h, json={"status": "en_produccion"})
    piece = client.post(f"/api/sales/{s['id']}/cancel", headers=h,
                        json={"keep_hours": True, "piece_outcome": "almacen"}).json()["warehouse_piece"]
    r = client.post(f"/api/warehouse/{piece['id']}/sell", headers=h, json={
        "promised_delivery_date": str(TODAY + timedelta(days=1)), "payment_method": "efectivo",
        "sale_source": "facebook"})
    assert r.status_code in (200, 201), r.text
    assert r.json()["sale_source"] == "facebook"


def test_dashboard_and_history_by_source(client, make):
    u = make.user()
    p, h = make.printer(u), make.headers(u)
    for source, price in (("instagram", 10000), ("instagram", 5000), ("facebook", 7000), (None, 3000)):
        extra = {"sale_source": source} if source else {}
        deliver(client, h, _create(client, h, p, price=price, **extra)["id"])
    # Un pedido abierto no cuenta (igual que el resto del Dashboard).
    _create(client, h, p, price=99999, sale_source="personal")

    r = client.get("/api/dashboard/by-source", headers=h, params={"date_from": str(TODAY), "date_to": str(TODAY)})
    assert r.status_code == 200, r.text
    rows = {row["sale_source"]: (row["jobs"], float(row["revenue"])) for row in r.json()}
    assert rows == {"instagram": (2, 15000.0), "facebook": (1, 7000.0), None: (1, 3000.0)}

    month = next(m for m in client.get("/api/history/monthly", headers=h).json()
                 if (m["year"], m["month"]) == (TODAY.year, TODAY.month))
    by_source = {k: (v["jobs"], float(v["revenue"])) for k, v in month["by_source"].items()}
    assert by_source == {"instagram": (2, 15000.0), "facebook": (1, 7000.0), "sin_registrar": (1, 3000.0)}


def test_sort_sales_sheet(client, make):
    u = make.user()
    p, h = make.printer(u), make.headers(u)
    for price, name in ((5000, "b"), (20000, "C"), (1000, "a")):
        _create(client, h, p, price=price, client_name=name)
    prices = lambda **kw: [float(s["price"]) for s in _list(client, h, **kw)["items"]]  # noqa: E731
    assert prices(sort="precio", direction="desc") == [20000, 5000, 1000]
    assert prices(sort="precio", direction="asc") == [1000, 5000, 20000]
    names = [s["client_name"] for s in _list(client, h, sort="cliente", direction="asc")["items"]]
    assert names == ["a", "b", "C"]  # sin distinguir mayúsculas
    # Sin parámetros: igual que antes (más recientes primero).
    assert _list(client, h)["items"][0]["client_name"] == "a"
    assert client.get("/api/sales", headers=h, params={"sort": "nada"}).status_code == 422


def test_sales_sheet_page_of_100(client, make):
    u = make.user()
    p, h = make.printer(u), make.headers(u)
    for i in range(105):
        _create(client, h, p, price=1000 + i)
    page = _list(client, h, limit=100)
    assert len(page["items"]) == 100 and page["total"] == 105
    ids = {s["id"] for s in page["items"]} | {s["id"] for s in _list(client, h, limit=100, offset=100)["items"]}
    assert len(ids) == 105  # sin repetidos ni saltados entre páginas
