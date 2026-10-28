"""Rendimiento por cuenta: solo la cuenta Empresa (ver services/performance)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_company
from app.models.user import User
from app.services.performance import account_performance

router = APIRouter(prefix="/api/performance", tags=["performance"])


def require_company(current_user: User = Depends(get_current_user)) -> User:
    if not is_company(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El rendimiento por cuenta es solo para la cuenta Empresa.")
    return current_user


@router.get("")
def performance(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_company),
):
    """Pedidos entregados del período, por cuenta y todas juntas, con su evolución mensual."""
    return account_performance(db, current_user, date_from, date_to)
