from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum
import re



class UserRole(str, Enum):
    admin = "admin"
    pentester = "pentester"
    read_only = "read_only"


class UserCreateSecure(BaseModel):
    username: str
    name: str
    role: UserRole
    location: str
    base_capacity: float = 1.0
    start_week: int = 1
    start_year: int = 2024
    end_week: Optional[int] = None
    end_year: Optional[int] = None


class UserUpdate(BaseModel):
    name: str
    role: UserRole
    location: str
    base_capacity: float
    start_week: int
    start_year: int
    end_week: Optional[int] = None
    end_year: Optional[int] = None


class EventCreate(BaseModel):
    user_id: Optional[str] = None
    event_type: str
    location: Optional[str] = None
    start_date: str
    end_date: str


class EventUpdate(BaseModel):
    user_id: Optional[str] = None
    event_type: str
    location: Optional[str] = None
    start_date: str
    end_date: str


class TestCreate(BaseModel):
    name: str
    service_id: str
    type: str
    credits_per_week: float
    duration_weeks: float
    asset_ids: Optional[List[str]] = []
    whitebox_category: Optional[str] = ""


class TestUpdate(BaseModel):
    name: str
    service_id: str
    credits_per_week: float
    duration_weeks: float
    status: Optional[str] = None
    whitebox_category: Optional[str] = ""
    drive_folder_id: Optional[str] = None
    drive_folder_url: Optional[str] = None
    intake_status: Optional[str] = 'Pending'
    restitution_status: Optional[str] = 'Pending'
    checklist_state: Optional[dict] = {}


class TestSchedule(BaseModel):
    start_week: Optional[int]
    start_year: Optional[int]


class AssignmentCreate(BaseModel):
    test_id: str
    user_id: str
    week_number: int
    year: int
    allocated_credits: float


class BulkTestCreate(BaseModel):
    asset_ids: List[str]


class AssetTrackingUpdate(BaseModel):
    pentest_queue: bool
    gost_service: Optional[str] = None
    whitebox_category: Optional[str] = None
    quarter_planned: Optional[str] = None
    year_planned: Optional[str] = None
    planned_with_ritm: Optional[bool] = None
    month_planned: Optional[str] = None
    week_planned: Optional[str] = None
    tested_2024_ritm: Optional[str] = None
    tested_2025_ritm: Optional[str] = None
    prevision_2027: Optional[str] = None
    confirmed_by_market: Optional[bool] = None
    status_manual_tracking: Optional[str] = None


class WhiteboxCategoryCreate(BaseModel):
    name: str
    target_goal: int


class WhiteboxCategoryUpdate(BaseModel):
    name: str
    target_goal: int


class MarketBase(BaseModel):
    code: str
    name: str
    language: Optional[str] = None
    region: Optional[str] = None
    is_active: bool = True
    description: Optional[str] = None


class MarketCreate(MarketBase):
    pass


class MarketUpdate(MarketBase):
    pass


class RegionSchema(BaseModel):
    regions: str
    is_active: bool = True


class MarketAssignment(BaseModel):
    market_id: str
    market_role: str


class MarketContactSchema(BaseModel):
    name: str
    email: str
    platform_role: str = 'market_user'
    is_active: bool = False
    assignments: List[MarketAssignment] = []


class ExtractedAsset(BaseModel):
    asset_id: Optional[str]
    name_mentioned: str
    market: Optional[str]
    confidence: int


class LuigiIntakeResult(BaseModel):
    note_id: str
    summary: str
    assets: List[ExtractedAsset]