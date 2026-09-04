"""Reglas de negocio fijas, no editables por el usuario.

Cambiar estos valores requiere un despliegue del backend, no una acción
de usuario ni un registro en base de datos.
"""

from decimal import Decimal
from typing import TypedDict

IVA_PERCENT = Decimal("19")
ELECTRICITY_RATE = Decimal("287")  # CLP / kWh
LABOR_RATE_PER_HOUR = Decimal("5000")  # CLP / hora de postprocesado


class MarginScenario(TypedDict):
    margin_percent: int
    label: str


MARGIN_SCENARIOS: list[MarginScenario] = [
    {"margin_percent": 100, "label": "Precio mayorista"},
    {"margin_percent": 150, "label": "Precio Normal"},
    {"margin_percent": 200, "label": "Precio Personalizado"},
]

MARGIN_SCENARIO_PERCENTS = {s["margin_percent"] for s in MARGIN_SCENARIOS}
