import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.watcher_assignment import WatcherAssignment
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    try:
        payload = decode_access_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("token type invalido")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido o expirado")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no valido")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.name != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de administrador")
    return current_user


def is_watcher(user: User) -> bool:
    return user.role.name == "watcher"


def require_not_watcher(current_user: User = Depends(get_current_user)) -> User:
    """Bloquea a los watchers en todo lo que sea administrar inventario e impresoras.
    Un watcher puede cotizar y registrar ventas con el inventario de sus usuarios
    asignados (eso se controla en ventas/calculadora), pero no editar ese inventario."""
    if is_watcher(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Como observador puedes ver inventario, cotizar y registrar ventas, pero no modificar inventario ni impresoras.",
        )
    return current_user


def readable_user_ids(db: Session, user: User) -> list[uuid.UUID]:
    """IDs cuyos datos puede LEER este usuario. Un usuario normal solo los propios;
    un watcher, los de los usuarios que el administrador le asignó (nunca los suyos,
    porque un watcher no tiene inventario propio)."""
    if not is_watcher(user):
        return [user.id]
    rows = (
        db.query(WatcherAssignment.observed_user_id)
        .filter(WatcherAssignment.watcher_user_id == user.id)
        .all()
    )
    return [row[0] for row in rows]
