import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.sale_supply import SaleSupply
from app.models.supply import Supply
from app.models.user import User
from app.schemas.supply import SupplyCreateRequest, SupplyResponse, SupplyUpdateRequest
from app.services.audit import log_event

router = APIRouter(prefix="/api/inventory/supplies", tags=["inventory"])


def _to_response(supply: Supply) -> SupplyResponse:
    low_stock = supply.min_alert_qty is not None and supply.quantity_available <= supply.min_alert_qty
    return SupplyResponse(
        id=supply.id,
        name=supply.name,
        category=supply.category,
        quantity_available=supply.quantity_available,
        min_alert_qty=supply.min_alert_qty,
        unit_cost=supply.unit_cost,
        is_active=supply.is_active,
        low_stock=low_stock,
    )


def _get_owned_supply(db: Session, supply_id: uuid.UUID, user: User) -> Supply:
    supply = db.query(Supply).filter(Supply.id == supply_id, Supply.user_id == user.id).first()
    if supply is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Insumo no encontrado")
    return supply


@router.get("", response_model=list[SupplyResponse])
def list_supplies(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Supply).filter(Supply.user_id == current_user.id)
    if not include_inactive:
        query = query.filter(Supply.is_active.is_(True))
    supplies = query.order_by(Supply.category, Supply.name).all()
    return [_to_response(s) for s in supplies]


@router.post("", response_model=SupplyResponse, status_code=status.HTTP_201_CREATED)
def create_supply(
    payload: SupplyCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supply = Supply(user_id=current_user.id, **payload.model_dump())
    db.add(supply)
    db.flush()
    log_event(
        db,
        user_id=current_user.id,
        event_type="INVENTORY_SUPPLY_CREATED",
        entity_type="supply",
        entity_id=supply.id,
        details={"name": supply.name},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(supply)
    return _to_response(supply)


@router.put("/{supply_id}", response_model=SupplyResponse)
def update_supply(
    supply_id: uuid.UUID,
    payload: SupplyUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supply = _get_owned_supply(db, supply_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(supply, field, value)

    log_event(
        db,
        user_id=current_user.id,
        event_type="INVENTORY_SUPPLY_UPDATED",
        entity_type="supply",
        entity_id=supply.id,
        details={"changes": {k: str(v) for k, v in changes.items()}},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(supply)
    return _to_response(supply)


@router.delete("/{supply_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supply(
    supply_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supply = _get_owned_supply(db, supply_id, current_user)
    has_sales = db.query(SaleSupply.id).filter(SaleSupply.supply_id == supply.id).first() is not None

    if has_sales:
        supply.is_active = False
        event_type = "INVENTORY_SUPPLY_DEACTIVATED"
    else:
        db.delete(supply)
        event_type = "INVENTORY_SUPPLY_DELETED"

    log_event(
        db,
        user_id=current_user.id,
        event_type=event_type,
        entity_type="supply",
        entity_id=supply_id,
        details={"name": supply.name},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
