import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_admin
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.schemas.audit_log import AuditLogPage, AuditLogResponse
from app.schemas.user import UserCreateRequest, UserResponse
from app.security import hash_password
from app.services.audit import log_event

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role.name,
        is_active=user.is_active,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=user.locked_until,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).options(joinedload(User.role)).order_by(User.created_at.desc()).all()
    return [_to_user_response(u) for u in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "El nombre de usuario ya existe")

    role = db.query(Role).filter(Role.name == payload.role).first()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rol inválido")

    user = User(username=payload.username, password_hash=hash_password(payload.password), role_id=role.id)
    db.add(user)
    db.flush()

    log_event(
        db,
        user_id=current_user.id,
        event_type="USER_CREATED",
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username, "role": role.name},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    user.role = role
    return _to_user_response(user)


@router.patch("/users/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes desactivar tu propia cuenta")

    user = db.query(User).options(joinedload(User.role)).get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    user.is_active = False
    log_event(
        db,
        user_id=current_user.id,
        event_type="USER_DEACTIVATED",
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _to_user_response(user)


@router.patch("/users/{user_id}/reactivate", response_model=UserResponse)
def reactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).options(joinedload(User.role)).get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    user.is_active = True
    user.failed_login_attempts = 0
    user.locked_until = None
    log_event(
        db,
        user_id=current_user.id,
        event_type="USER_REACTIVATED",
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _to_user_response(user)


@router.get("/audit-logs", response_model=AuditLogPage)
def list_audit_logs(
    db: Session = Depends(get_db),
    user_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(AuditLog)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if event_type is not None:
        query = query.filter(AuditLog.event_type == event_type)
    if date_from is not None:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        query = query.filter(AuditLog.created_at <= date_to)

    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    user_ids = {row.user_id for row in rows if row.user_id is not None}
    usernames = {}
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            usernames[u.id] = u.username

    items = [
        AuditLogResponse(
            id=row.id,
            user_id=row.user_id,
            username=usernames.get(row.user_id),
            event_type=row.event_type,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            details=row.details,
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return AuditLogPage(items=items, total=total)
