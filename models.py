from pydantic import BaseModel, field_validator
from typing import Optional, List
from enum import Enum
import re


def enforce_password_policy(password: str) -> str:
    """Enforces minimum length and character complexity rules."""
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ValueError("Password must contain at least one special character (!@#$%^&* etc).")
    return password


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


# The user payload when they click the secure link
class UserSetupPassword(BaseModel):
    token: str
    new_password: str
    totp_code: str  # Enforcing 2FA on setup

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v):
        return enforce_password_policy(v)


class FirstAdminSetup(BaseModel):
    username: str
    password: str
    name: str
    location: str

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        return enforce_password_policy(v)


class UserUpdate(BaseModel):
    name: str
    role: UserRole
    location: str
    base_capacity: float
    start_week: int


class PasswordChange(BaseModel):
    old_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v):
        return enforce_password_policy(v)


class AdminPasswordReset(BaseModel):
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v):
        return enforce_password_policy(v)


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