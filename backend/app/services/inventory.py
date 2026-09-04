from decimal import ROUND_HALF_UP, Decimal

from app.models.filament import Filament
from app.models.supply import Supply


def filament_stock_status(filament: Filament) -> tuple[Decimal, str]:
    stock_percent = Decimal(0)
    if filament.initial_stock_g and filament.initial_stock_g > 0:
        stock_percent = (filament.available_g / filament.initial_stock_g * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    if filament.available_g <= 0:
        status = "vacio"
    elif filament.available_g <= filament.min_alert_g * Decimal("0.5"):
        status = "critico"
    elif filament.available_g <= filament.min_alert_g:
        status = "alerta"
    else:
        status = "disponible"

    return stock_percent, status


class InsufficientStockError(Exception):
    pass


def consume_filament(filament: Filament, grams: Decimal) -> None:
    if grams <= 0:
        return
    if filament.available_g < grams:
        raise InsufficientStockError(
            f"Stock insuficiente de filamento '{filament.brand} {filament.color}': "
            f"disponible {filament.available_g}g, solicitado {grams}g"
        )
    filament.used_g += grams
    filament.available_g -= grams


def restore_filament(filament: Filament, grams: Decimal) -> None:
    if grams <= 0:
        return
    filament.used_g -= grams
    filament.available_g += grams


def consume_supply(supply: Supply, quantity: Decimal) -> None:
    if quantity <= 0:
        return
    if supply.quantity_available < quantity:
        raise InsufficientStockError(
            f"Stock insuficiente de insumo '{supply.name}': "
            f"disponible {supply.quantity_available}, solicitado {quantity}"
        )
    supply.quantity_available -= quantity


def restore_supply(supply: Supply, quantity: Decimal) -> None:
    if quantity <= 0:
        return
    supply.quantity_available += quantity
