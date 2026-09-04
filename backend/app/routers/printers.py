import uuid
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.printer import Printer
from app.models.sale import Sale
from app.models.user import User
from app.schemas.printer import PrinterCreateRequest, PrinterResponse, PrinterUpdateRequest
from app.services.audit import log_event
from app.services.calculator import calculate_depreciation_cost_per_hour

router = APIRouter(prefix="/api/printers", tags=["printers"])


def _to_response(printer: Printer) -> PrinterResponse:
    life_used_percent = Decimal(0)
    if printer.lifetime_hours and printer.lifetime_hours > 0:
        life_used_percent = (printer.hours_used / printer.lifetime_hours * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    life_remaining = max(printer.lifetime_hours - printer.hours_used, Decimal(0))
    return PrinterResponse(
        id=printer.id,
        name=printer.name,
        purchase_value=printer.purchase_value,
        lifetime_hours=printer.lifetime_hours,
        power_kw=printer.power_kw,
        hours_used=printer.hours_used,
        depreciation_cost_per_hour=printer.depreciation_cost_per_hour,
        is_active=printer.is_active,
        life_used_percent=life_used_percent,
        life_remaining_hours=life_remaining,
    )


def _get_owned_printer(db: Session, printer_id: uuid.UUID, user: User) -> Printer:
    printer = db.query(Printer).filter(Printer.id == printer_id, Printer.user_id == user.id).first()
    if printer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Impresora no encontrada")
    return printer


@router.get("", response_model=list[PrinterResponse])
def list_printers(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Printer).filter(Printer.user_id == current_user.id)
    if not include_inactive:
        query = query.filter(Printer.is_active.is_(True))
    printers = query.order_by(Printer.name).all()
    return [_to_response(p) for p in printers]


@router.post("", response_model=PrinterResponse, status_code=status.HTTP_201_CREATED)
def create_printer(
    payload: PrinterCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    depreciation = calculate_depreciation_cost_per_hour(payload.purchase_value, payload.lifetime_hours)
    printer = Printer(
        user_id=current_user.id,
        name=payload.name,
        purchase_value=payload.purchase_value,
        lifetime_hours=payload.lifetime_hours,
        power_kw=payload.power_kw,
        depreciation_cost_per_hour=depreciation,
    )
    db.add(printer)
    db.flush()
    log_event(
        db,
        user_id=current_user.id,
        event_type="PRINTER_CREATED",
        entity_type="printer",
        entity_id=printer.id,
        details={"name": printer.name},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(printer)
    return _to_response(printer)


@router.put("/{printer_id}", response_model=PrinterResponse)
def update_printer(
    printer_id: uuid.UUID,
    payload: PrinterUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    printer = _get_owned_printer(db, printer_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(printer, field, value)
    if "purchase_value" in changes or "lifetime_hours" in changes:
        printer.depreciation_cost_per_hour = calculate_depreciation_cost_per_hour(
            printer.purchase_value, printer.lifetime_hours
        )

    log_event(
        db,
        user_id=current_user.id,
        event_type="PRINTER_UPDATED",
        entity_type="printer",
        entity_id=printer.id,
        details={"changes": {k: str(v) for k, v in changes.items()}},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(printer)
    return _to_response(printer)


@router.delete("/{printer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_printer(
    printer_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    printer = _get_owned_printer(db, printer_id, current_user)
    has_sales = db.query(Sale.id).filter(Sale.printer_id == printer.id).first() is not None

    if has_sales:
        printer.is_active = False
        event_type = "PRINTER_DEACTIVATED"
    else:
        db.delete(printer)
        event_type = "PRINTER_DELETED"

    log_event(
        db,
        user_id=current_user.id,
        event_type=event_type,
        entity_type="printer",
        entity_id=printer_id,
        details={"name": printer.name},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
