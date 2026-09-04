from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDMixin


class FilamentBrand(UUIDMixin, Base):
    __tablename__ = "filament_brands"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class FilamentMaterial(UUIDMixin, Base):
    __tablename__ = "filament_materials"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class FilamentColor(UUIDMixin, Base):
    __tablename__ = "filament_colors"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    hex_color: Mapped[str] = mapped_column(Text, nullable=False)
