"""Asistente IA: acceso solo para ASSISTANT_USERS y contexto con los datos de esas cuentas."""
import io
import json

from conftest import deliver, sale_payload

from app.config import settings
from app.services import assistant


class FakeGemini:
    """Reemplaza urlopen: guarda lo enviado y responde un texto fijo."""

    def __init__(self, reply="Respuesta de prueba"):
        self.reply = reply
        self.sent = None

    def __call__(self, request, timeout=None):
        self.sent = json.loads(request.data.decode("utf-8"))
        body = {"candidates": [{"content": {"parts": [{"text": "pensando", "thought": True}, {"text": self.reply}]}}]}
        return io.BytesIO(json.dumps(body).encode("utf-8"))


def _setup(monkeypatch, make):
    partner, outsider = make.user(name="socio"), make.user(name="otro")
    monkeypatch.setattr(settings, "assistant_users", f"{partner.username},Nadie")
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    fake = FakeGemini()
    monkeypatch.setattr(assistant.urllib.request, "urlopen", fake)
    return partner, outsider, fake


def _ask(client, h, text="¿Cuánto vendí?"):
    return client.post("/api/assistant/chat", headers=h, json={"messages": [{"role": "user", "text": text}]})


def test_access_only_for_assistant_users(client, make, monkeypatch):
    partner, outsider, _ = _setup(monkeypatch, make)
    assert client.get("/api/assistant/access", headers=make.headers(partner)).json() == {
        "enabled": True, "configured": True}
    assert client.get("/api/assistant/access", headers=make.headers(outsider)).json()["enabled"] is False
    assert _ask(client, make.headers(outsider)).status_code == 403


def test_context_has_own_data_and_not_others(client, make, monkeypatch):
    partner, outsider, fake = _setup(monkeypatch, make)
    p = make.printer(partner, name="Bambu A1")
    h = make.headers(partner)
    r = client.post("/api/sales", headers=h, json=sale_payload(p, client_name="Cliente Visible", price=12000))
    deliver(client, h, r.json()["id"])
    op = make.printer(outsider, name="Ajena")
    client.post("/api/sales", headers=make.headers(outsider), json=sale_payload(op, client_name="Cliente Oculto"))

    r = _ask(client, h)
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "Respuesta de prueba"  # sin el texto de "pensamiento"
    system = fake.sent["system_instruction"]["parts"][0]["text"]
    assert "Cliente Visible" in system and "Bambu A1" in system
    assert "Cliente Oculto" not in system and "Ajena" not in system
    assert fake.sent["contents"] == [{"role": "user", "parts": [{"text": "¿Cuánto vendí?"}]}]


def test_history_must_start_with_user_and_end_with_question(client, make, monkeypatch):
    partner, _, fake = _setup(monkeypatch, make)
    h = make.headers(partner)
    msgs = [{"role": "assistant", "text": "Hola"}, {"role": "user", "text": "a"},
            {"role": "assistant", "text": "b"}, {"role": "user", "text": "c"}]
    assert client.post("/api/assistant/chat", headers=h, json={"messages": msgs}).status_code == 200
    assert [c["role"] for c in fake.sent["contents"]] == ["user", "model", "user"]
    r = client.post("/api/assistant/chat", headers=h, json={"messages": msgs[:3]})
    assert r.status_code == 400


def test_missing_key_gives_clear_error(client, make, monkeypatch):
    partner, _, _ = _setup(monkeypatch, make)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    r = _ask(client, make.headers(partner))
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
