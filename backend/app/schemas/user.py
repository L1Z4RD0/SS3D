import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(admin|user|watcher)$")


class WatcherAssignmentsRequest(BaseModel):
    """Lista completa de usuarios que este watcher puede observar (reemplaza la anterior)."""

    observed_user_ids: list[uuid.UUID] = Field(default_factory=list)


class WatcherAssignmentsResponse(BaseModel):
    watcher_user_id: uuid.UUID
    observed_user_ids: list[uuid.UUID]


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    is_active: bool
    failed_login_attempts: int
    locked_until: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
