from pydantic import BaseModel
from typing import Optional, List



class UserCreateSecure(BaseModel):
    username: str
    password: str
    name: str
    role: str
    location: str
    base_capacity: float = 1.0
    start_week: int = 1


class FirstAdminSetup(BaseModel):
    username: str
    password: str
    name: str
    location: str


class UserUpdate(BaseModel):
    name: str
    role: str
    location: str
    base_capacity: float
    start_week: int


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class AdminPasswordReset(BaseModel):
    new_password: str


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