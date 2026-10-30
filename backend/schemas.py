from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal
from datetime import datetime, timedelta, timezone


# Pydantic model for incoming task data
class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(default="", max_length=500)
    priority: Literal["low", "medium", "high"]
    due_date: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    priority: Literal["low", "medium", "high"] | None = None
    status: str | None = None


# Pydantic model for outgoing task data
class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    # completed: bool
    priority: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class TaskAssign(BaseModel):
    assigned_to_id: int = Field(gt=0)
