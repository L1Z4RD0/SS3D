import uuid

from sqlalchemy.orm import Session

from app.models.calculator_settings import DEFAULT_MARGIN_SCENARIOS, CalculatorSettings


def get_or_create_settings(db: Session, user_id: uuid.UUID) -> CalculatorSettings:
    settings = db.query(CalculatorSettings).filter(CalculatorSettings.user_id == user_id).first()
    if settings is None:
        settings = CalculatorSettings(
            user_id=user_id,
            electricity_rate=0,
            labor_rate_per_hour=0,
            iva_percent=19,
            margin_scenarios=list(DEFAULT_MARGIN_SCENARIOS),
        )
        db.add(settings)
        db.flush()
    return settings
