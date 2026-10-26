"""Bot de Discord: no perder avisos cuando llegan muchos pedidos seguidos.

No se llama a Discord de verdad: se reemplaza urllib.request.urlopen por un falso que
responde 429 (límite de velocidad) o 200, y time.sleep por una función que solo registra."""
import io
import json
import threading
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message

import pytest
from conftest import sale_payload

from app.config import settings
from app.database import SessionLocal
from app.models.discord_message import DiscordMessage
from app.models.sale import Sale
from app.services import discord


class FakeResponse:
    def __init__(self, body, headers=None):
        self._body = json.dumps(body).encode()
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def rate_limited(retry_after=0.3):
    headers = Message()
    headers["Retry-After"] = str(retry_after)
    body = io.BytesIO(json.dumps({"retry_after": retry_after}).encode())
    return urllib.error.HTTPError("https://discord.test", 429, "Too Many Requests", headers, body)


@pytest.fixture
def fake_discord(monkeypatch):
    """Discord falso: devuelve ids crecientes; `script` permite fallar las primeras llamadas."""
    state = {"calls": [], "sleeps": [], "script": [], "active": 0, "max_active": 0, "lock": threading.Lock()}

    def urlopen(request, timeout=None):
        with state["lock"]:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        try:
            state["calls"].append((request.get_method(), request.full_url))
            if state["script"]:
                outcome = state["script"].pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
            return FakeResponse({"id": str(len(state["calls"]))})
        finally:
            with state["lock"]:
                state["active"] -= 1

    monkeypatch.setattr(discord.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(discord.time, "sleep", lambda s: state["sleeps"].append(s))
    monkeypatch.setattr(settings, "discord_webhook_url", "https://discord.test/api/webhooks/1/x")
    return state


def _notified_user(make, monkeypatch):
    u = make.user(name="diego")
    monkeypatch.setattr(settings, "discord_notify_users", u.username)
    return u


def _sale(client, make, u):
    r = client.post("/api/sales", headers=make.headers(u), json=sale_payload(make.printer(u)))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _linked(sale_id):
    with SessionLocal() as db:
        return db.get(DiscordMessage, sale_id) is not None


def test_rate_limited_announcement_is_retried(client, make, monkeypatch, fake_discord):
    u = _notified_user(make, monkeypatch)
    fake_discord["script"] = [rate_limited(1.2), rate_limited(1.2)]
    sale_id = _sale(client, make, u)  # TestClient corre la tarea en segundo plano al responder
    assert _linked(sale_id)
    assert fake_discord["sleeps"][:2] == [1.2, 1.2]  # la espera que pidió Discord
    assert len(fake_discord["calls"]) == 3


def test_burst_of_orders_all_published_one_at_a_time(client, make, monkeypatch, fake_discord):
    u = _notified_user(make, monkeypatch)
    ids = [_sale(client, make, u) for _ in range(3)]
    fake_discord["calls"].clear()
    fake_discord["max_active"] = 0
    # Simula la ráfaga: varios avisos a la vez en hilos distintos, como BackgroundTasks.
    with SessionLocal() as db:
        db.query(DiscordMessage).filter(DiscordMessage.sale_id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    threads = [threading.Thread(target=discord.announce_order, args=(i,)) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(_linked(i) for i in ids)
    assert fake_discord["max_active"] == 1  # nunca dos envíos al mismo tiempo


def test_lost_announcement_is_published_on_next_change(client, make, monkeypatch, fake_discord):
    u = _notified_user(make, monkeypatch)
    # Discord rechaza todos los intentos del aviso inicial.
    fake_discord["script"] = [rate_limited(0.1)] * discord.MAX_ATTEMPTS
    sale_id = _sale(client, make, u)
    assert not _linked(sale_id)
    r = client.post(f"/api/sales/{sale_id}/status", headers=make.headers(u), json={"status": "en_produccion"})
    assert r.status_code == 200, r.text
    assert _linked(sale_id)


def test_old_unannounced_order_is_not_published_on_edit(client, make, monkeypatch, fake_discord):
    u = make.user(name="diego")
    sale_id = _sale(client, make, u)  # creado antes de que el usuario estuviera en la lista
    monkeypatch.setattr(settings, "discord_notify_users", u.username)
    with SessionLocal() as db:
        db.get(Sale, sale_id).created_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()
    client.post(f"/api/sales/{sale_id}/status", headers=make.headers(u), json={"status": "en_produccion"})
    assert not _linked(sale_id)


def test_client_errors_are_not_retried(client, make, monkeypatch, fake_discord):
    u = _notified_user(make, monkeypatch)
    not_found = urllib.error.HTTPError("https://discord.test", 404, "Not Found", Message(), io.BytesIO(b"{}"))
    fake_discord["script"] = [not_found]
    sale_id = _sale(client, make, u)
    assert not _linked(sale_id)
    assert fake_discord["sleeps"] == []
