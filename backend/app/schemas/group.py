"""포트폴리오 그룹 스키마 — Pydantic v2"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(max_length=100)
    description: str | None = None
    sort_order: int = 0


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    sort_order: int | None = None


class GroupResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    sort_order: int
    created_at: datetime
    asset_count: int

    model_config = {"from_attributes": True}


class GroupListResponse(BaseModel):
    groups: list[GroupResponse]
    total: int
