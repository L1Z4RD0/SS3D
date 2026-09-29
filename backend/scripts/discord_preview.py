"""Publica en el canal de Discord una tarjeta de ejemplo y la hace pasar por todos los
estados (verde -> rojo), para ver el diseño sin crear pedidos reales. No toca la base.

    python scripts/discord_preview.py "https://discord.com/api/webhooks/..." [https://tu-app.vercel.app]
"""
import os
import sys
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# La configuración exige estas variables; la vista previa no usa la base de datos.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://preview@127.0.0.1:1/preview")
os.environ.setdefault("SECRET_KEY", "preview")

from app.config import settings  # noqa: E402
from app.schemas.sale import SaleFilamentResponse, SaleResponse  # noqa: E402
from app.services import discord  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    settings.discord_webhook_url = sys.argv[1]
    settings.app_url = sys.argv[2] if len(sys.argv) > 2 else settings.app_url

    today = date.today()
    sale = SaleResponse.model_construct(
        id=uuid.uuid4(),
        client_name="Cliente de prueba",
        buyer_name="María",
        owner_username="Diego",
        created_by_username="Sntg",
        printer_name="Bambu Lab A1",
        filaments_used=[
            SaleFilamentResponse(filament_id=uuid.uuid4(), filament_label="PLA Negro mate", grams_used=Decimal("120"),
                                 material_cost_snapshot=Decimal(0)),
            SaleFilamentResponse(filament_id=uuid.uuid4(), filament_label="PETG Rojo", grams_used=Decimal("40"),
                                 material_cost_snapshot=Decimal(0)),
        ],
        filament_label=None,
        warehouse_item_id=None,
        price=Decimal("25000"),
        payment_method="transferencia",
        notes="Esto es una vista previa: 10 llaveros con logo.",
        cancel_reason=None,
        status="pendiente",
        promised_delivery_date=today + timedelta(days=4),
        delivered_date=None,
    )
    message_id = discord._deliver(sale)
    print(f"Publicada (mensaje {message_id}). Recorriendo estados cada 4 s…")
    for status in ("en_produccion", "lista", "entregada"):
        time.sleep(4)
        sale = sale.model_copy(update={"status": status, "delivered_date": today if status == "entregada" else None})
        discord._deliver(sale, message_id=message_id)
        print(f"  -> {status}")
    print("Listo. Puedes borrar el mensaje de prueba en Discord.")


if __name__ == "__main__":
    main()
