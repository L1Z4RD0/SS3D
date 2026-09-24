import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload

from app.constants import IVA_PERCENT
from app.database import get_db
from app.dependencies import get_current_user
from app.models.quote import Quote, QuoteItem
from app.models.user import User
from app.schemas.quote import QuoteCreateRequest, QuotePage, QuoteResponse
from app.services.audit import log_event
from app.services.calculator import money

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


def _quote_query(db: Session, user: User):
    return db.query(Quote).options(joinedload(Quote.items)).filter(Quote.user_id == user.id)


@router.get("", response_model=QuotePage)
def list_quotes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = _quote_query(db, current_user)
    total = query.count()
    rows = query.order_by(Quote.quote_number.desc()).offset(offset).limit(limit).all()
    return QuotePage(items=[QuoteResponse.model_validate(q) for q in rows], total=total)


@router.get("/{quote_id}", response_model=QuoteResponse)
def get_quote(quote_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    quote = _quote_query(db, current_user).filter(Quote.id == quote_id).first()
    if quote is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cotización no encontrada")
    return QuoteResponse.model_validate(quote)


@router.post("", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
def create_quote(
    payload: QuoteCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Contador propio del usuario, incrementado de forma atómica (UPDATE ... RETURNING
    # toma el lock de la fila). Antes era MAX(quote_number)+1, que reiniciaba la
    # numeración al borrar cotizaciones y podía repetir códigos ya entregados.
    next_number = db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(last_quote_number=User.last_quote_number + 1)
        .returning(User.last_quote_number)
    ).scalar_one()

    items = [
        QuoteItem(
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=money(item.quantity * item.unit_price),
        )
        for item in payload.items
    ]
    subtotal = money(sum((i.subtotal for i in items), 0))
    iva_amount = money(subtotal * IVA_PERCENT / 100)
    total = money(subtotal + iva_amount)

    quote = Quote(
        user_id=current_user.id,
        quote_number=next_number,
        client_name=payload.client_name,
        quote_date=payload.quote_date,
        subtotal=subtotal,
        iva_percent=IVA_PERCENT,
        iva_amount=iva_amount,
        total=total,
        document_snapshot=payload.document_snapshot,
        items=items,
    )
    db.add(quote)
    db.flush()

    log_event(
        db,
        user_id=current_user.id,
        event_type="QUOTE_CREATED",
        entity_type="quote",
        entity_id=quote.id,
        details={"quote_number": quote.quote_number, "client_name": quote.client_name, "total": str(quote.total)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return QuoteResponse.model_validate(quote)
