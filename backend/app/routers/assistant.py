"""Asistente IA de consultas: solo para las cuentas de ASSISTANT_USERS (ver services/assistant)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.assistant import AssistantError, ask, can_use_assistant

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

# Cuántos mensajes previos de la conversación se reenvían como memoria.
HISTORY_LIMIT = 20


def require_assistant_access(current_user: User = Depends(get_current_user)) -> User:
    if not can_use_assistant(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El asistente IA es solo para las cuentas del emprendimiento.")
    return current_user


class AssistantAccessResponse(BaseModel):
    enabled: bool
    configured: bool


@router.get("/access", response_model=AssistantAccessResponse)
def assistant_access(current_user: User = Depends(get_current_user)):
    """Si este usuario ve la burbuja del asistente."""
    return AssistantAccessResponse(enabled=can_use_assistant(current_user), configured=bool(settings.gemini_api_key))


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_assistant_access),
):
    messages = [m.model_dump() for m in payload.messages[-HISTORY_LIMIT:]]
    # Gemini exige que la conversación empiece con el usuario.
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if not messages or messages[-1]["role"] != "user":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta la pregunta.")
    try:
        return ChatResponse(reply=ask(db, current_user, messages))
    except AssistantError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
