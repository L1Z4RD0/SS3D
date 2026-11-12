"""Precio de la impresión y delivery, por separado.

`Sale.base_price` / `total_price` guardan lo que paga el cliente EN TOTAL: la impresión más
el delivery (shipping_cost). El delivery no es ingreso del negocio: se le devuelve a quien lo
llevó (ver Reparto). Por eso las pantallas muestran el precio de la impresión (total −
delivery) y el delivery aparte, y los ingresos/costos del Dashboard, el Historial y
Rendimiento no lo incluyen. La ganancia no cambia: el delivery entra y sale por el mismo monto.

Un regalo (precio $0) con delivery no lo cobra: ahí el delivery sigue siendo un costo. Por
eso lo "cobrado por delivery" nunca supera el precio.
"""
from decimal import Decimal

from sqlalchemy import func

from app.models.sale import Sale

# Expresiones SQL (para sumar en consultas).
DELIVERY_CHARGED = func.least(Sale.shipping_cost, Sale.base_price)
PIECE_REVENUE = Sale.base_price - DELIVERY_CHARGED
COST_WITHOUT_DELIVERY = Sale.total_cost - DELIVERY_CHARGED


def delivery_charged(sale: Sale) -> Decimal:
    """Parte del precio que es delivery cobrado al cliente."""
    return min(sale.shipping_cost or Decimal(0), sale.base_price or Decimal(0))


def piece_price(sale: Sale) -> Decimal:
    """Precio de la impresión: lo cobrado menos el delivery."""
    return sale.base_price - delivery_charged(sale)


def cost_without_delivery(sale: Sale) -> Decimal:
    return sale.total_cost - delivery_charged(sale)


def total_from_piece_price(piece: Decimal, shipping_cost: Decimal) -> Decimal:
    """Total a cobrar cuando el usuario escribe el precio de la impresión."""
    return piece + (shipping_cost or Decimal(0))
