from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models import SourceType


class SourceCreate(BaseModel):
    name: str
    url: str
    type: SourceType = SourceType.RSS
    category: Optional[str] = None
    html_item_selector: Optional[str] = None
    html_title_selector: Optional[str] = None
    html_link_selector: Optional[str] = None


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    html_item_selector: Optional[str] = None
    html_title_selector: Optional[str] = None
    html_link_selector: Optional[str] = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    type: SourceType
    category: Optional[str] = None
    is_active: bool
    created_at: datetime


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    title: str
    link: str
    summary: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: datetime
    is_read: bool
    is_deferred: bool
    is_sent: bool
