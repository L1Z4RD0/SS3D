import uuid

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ObservedUserResponse(BaseModel):
    id: uuid.UUID
    username: str
    # La propia cuenta Empresa (su inventario aparece junto al de los socios que observa).
    is_self: bool = False


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    is_active: bool
    is_company: bool = False

    model_config = {"from_attributes": True}
