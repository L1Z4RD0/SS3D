from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import utcnow


class DiscordMessage(Base):
    """Aviso de Discord que anunció un pedido, para editarlo cuando el pedido cambia.

    Tabla aparte (y sin FK a sales) a propósito: si falta o falla, solo se pierde el aviso,
    nunca el pedido. Al eliminar el pedido, el aviso se marca como eliminado y recién ahí
    se borra la fila."""

    __tablename__ = "discord_messages"

    sale_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    message_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
