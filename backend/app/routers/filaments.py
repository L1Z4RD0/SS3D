import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.filament import Filament
from app.models.sale import Sale
from app.models.user import User
from app.schemas.filament import FilamentCreateRequest, FilamentResponse, FilamentUpdateRequest
from app.services.audit import log_event
from app.services.inventory import filament_stock_status

router = APIRouter(prefix="/api/inventory/filaments", tags=["inventory"])


def _to_response(filament: Filament) -> FilamentResponse:
    stock_percent, stock_status = filament_stock_status(filament)
    return FilamentResponse(
        id=filament.id,
        brand=filament.brand,
        type=filament.type,
        color=filament.color,
        sku=filament.sku,
        entry_date=filament.entry_date,
        spool_weight_g=filament.spool_weight_g,
        initial_stock_g=filament.initial_stock_g,
        used_g=filament.used_g,
        available_g=filament.available_g,
        min_alert_g=filament.min_alert_g,
        spool_price=filament.spool_price,
        is_active=filament.is_active,
        stock_percent=stock_percent,
        stock_status=stock_status,
    )


def _get_owned_filament(db: Session, filament_id: uuid.UUID, user: User) -> Filament:
    filament = db.query(Filament).filter(Filament.id == filament_id, Filament.user_id == user.id).first()
    if filament is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filamento no encontrado")
    return filament


@router.get("", response_model=list[FilamentResponse])
def list_filaments(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Filament).filter(Filament.user_id == current_user.id)
    if not include_inactive:
        query = query.filter(Filament.is_active.is_(True))
    filaments = query.order_by(Filament.brand, Filament.color).all()
    return [_to_response(f) for f in filaments]


@router.post("", response_model=FilamentResponse, status_code=status.HTTP_201_CREATED)
def create_filament(
    payload: FilamentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filament = Filament(
        user_id=current_user.id,
        brand=payload.brand,
        type=payload.type,
        color=payload.color,
        sku=payload.sku,
        entry_date=payload.entry_date,
        spool_weight_g=payload.spool_weight_g,
        initial_stock_g=payload.initial_stock_g,
        used_g=0,
        available_g=payload.initial_stock_g,
        min_alert_g=payload.min_alert_g,
        spool_price=payload.spool_price,
    )
    db.add(filament)
    db.flush()
    log_event(
        db,
        user_id=current_user.id,
        event_type="INVENTORY_FILAMENT_CREATED",
        entity_type="filament",
        entity_id=filament.id,
        details={"brand": filament.brand, "color": filament.color},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(filament)
    return _to_response(filament)


@router.put("/{filament_id}", response_model=FilamentResponse)
def update_filament(
    filament_id: uuid.UUID,
    payload: FilamentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filament = _get_owned_filament(db, filament_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(filament, field, value)

    if "initial_stock_g" in changes:
        filament.available_g = filament.initial_stock_g - filament.used_g

    log_event(
        db,
        user_id=current_user.id,
        event_type="INVENTORY_FILAMENT_UPDATED",
        entity_type="filament",
        entity_id=filament.id,
        details={"changes": {k: str(v) for k, v in changes.items()}},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(filament)
    return _to_response(filament)


@router.delete("/{filament_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_filament(
    filament_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filament = _get_owned_filament(db, filament_id, current_user)
    has_sales = db.query(Sale.id).filter(Sale.filament_id == filament.id).first() is not None

    if has_sales:
        filament.is_active = False
        event_type = "INVENTORY_FILAMENT_DEACTIVATED"
    else:
        db.delete(filament)
        event_type = "INVENTORY_FILAMENT_DELETED"

    log_event(
        db,
        user_id=current_user.id,
        event_type=event_type,
        entity_type="filament",
        entity_id=filament_id,
        details={"brand": filament.brand, "color": filament.color},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
