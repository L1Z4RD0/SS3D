from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.security import (
    LOCKOUT_DURATION,
    MAX_FAILED_LOGIN_ATTEMPTS,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.services.audit import log_event

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
        secure=settings.cookie_secure,
        max_age=settings.refresh_token_expire_days * 86400,
        path=REFRESH_COOKIE_PATH,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.username == payload.username)
        .first()
    )

    if user is None:
        log_event(
            db,
            user_id=None,
            event_type="LOGIN_FAILED",
            details={"username": payload.username, "reason": "user_not_found"},
            ip_address=ip,
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")

    now = datetime.now(timezone.utc)

    if user.locked_until and user.locked_until > now:
        log_event(db, user_id=user.id, event_type="LOGIN_FAILED", details={"reason": "account_locked"}, ip_address=ip)
        db.commit()
        raise HTTPException(status.HTTP_423_LOCKED, "Cuenta bloqueada temporalmente por intentos fallidos")

    if not user.is_active:
        log_event(db, user_id=user.id, event_type="LOGIN_FAILED", details={"reason": "inactive"}, ip_address=ip)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cuenta desactivada")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        locked = user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS
        if locked:
            user.locked_until = now + LOCKOUT_DURATION
            log_event(
                db,
                user_id=user.id,
                event_type="ACCOUNT_LOCKED",
                details={"locked_until": user.locked_until.isoformat()},
                ip_address=ip,
            )
        log_event(
            db,
            user_id=user.id,
            event_type="LOGIN_FAILED",
            details={"reason": "bad_password", "attempts": user.failed_login_attempts},
            ip_address=ip,
        )
        db.commit()
        if locked:
            raise HTTPException(
                status.HTTP_423_LOCKED, "Cuenta bloqueada por 1 hora tras 3 intentos fallidos consecutivos"
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")

    user.failed_login_attempts = 0
    user.locked_until = None

    access_token = create_access_token(user.id, user.role.name)
    raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_token_expiry(),
            user_agent=request.headers.get("user-agent"),
        )
    )
    log_event(db, user_id=user.id, event_type="LOGIN_SUCCESS", ip_address=ip)
    db.commit()

    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No hay sesión activa")

    token_hash = hash_refresh_token(raw_token)
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    now = datetime.now(timezone.utc)

    if row is None or row.revoked_at is not None or row.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o expirada")

    user = db.query(User).options(joinedload(User.role)).get(row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no válido")

    row.revoked_at = now
    new_raw = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(new_raw),
            expires_at=refresh_token_expiry(),
            user_agent=request.headers.get("user-agent"),
        )
    )
    db.commit()

    access_token = create_access_token(user.id, user.role.name)
    _set_refresh_cookie(response, new_raw)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        if row and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)

    log_event(db, user_id=current_user.id, event_type="LOGOUT", ip_address=_client_ip(request))
    db.commit()
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        samesite=settings.refresh_cookie_samesite,
    )


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: User = Depends(get_current_user)):
    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role.name,
        is_active=current_user.is_active,
    )
