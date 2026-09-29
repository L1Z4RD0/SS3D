import json
import logging
import urllib.request

from app.config import settings
from app.schemas.sale import SaleResponse

logger = logging.getLogger(__name__)


def notify_order_scheduled(sale: SaleResponse) -> None:
    """Avisa en Discord que se agendó un pedido. Corre en segundo plano después de
    responder, y nunca lanza: si Discord falla, el pedido ya quedó creado igual."""
    try:
        if not settings.discord_webhook_url:
            return
        created_by = sale.created_by_username or ""
        if created_by.lower() not in settings.discord_notify_users_set:
            return

        fields = [
            {"name": "Cliente", "value": sale.client_name, "inline": True},
            {"name": "Entrega", "value": sale.promised_delivery_date.strftime("%d-%m-%Y"), "inline": True},
            {"name": "Precio", "value": f"${sale.price:,.0f}".replace(",", "."), "inline": True},
            {"name": "Registrado por", "value": created_by, "inline": True},
            {"name": "Inventario de", "value": sale.owner_username, "inline": True},
        ]
        payload = {"embeds": [{"title": "📅 Nuevo pedido agendado", "color": 0x5865F2, "fields": fields}]}
        request = urllib.request.Request(
            settings.discord_webhook_url,
            data=json.dumps(payload).encode(),
            # Discord (Cloudflare) rechaza con 403 el User-Agent por defecto de urllib.
            headers={"Content-Type": "application/json", "User-Agent": "SS3D-Notifier/1.0"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=5).close()
    except Exception:
        logger.exception("No se pudo notificar el pedido a Discord")
