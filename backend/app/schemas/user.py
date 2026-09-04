import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(admin|user)$")


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    is_active: bool
    failed_login_attempts: int
    locked_until: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
