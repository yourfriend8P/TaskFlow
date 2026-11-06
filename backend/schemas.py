from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal
from datetime import datetime


# Pydantic model for incoming task data
class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(default="", max_length=500)
    priority: Literal["low", "medium", "high"]
    due_date: datetime | None = None
    project_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["todo", "in_progress", "completed"] | None = None
    project_id: int | None = None


# Pydantic model for outgoing task data
class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    status: Literal["todo", "in_progress", "completed"]
    priority: Literal["low", "medium", "high"]
    project_id: int | None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    description: str = Field(default="", max_length=1000)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    created_by_id: int
    created_at: datetime


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=1000)


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


# To activate or deactivate a user performed by admin
class UserStatusUpdate(BaseModel):
    is_active: bool


# To update the role of a user performed by admin
class UserRoleUpdate(BaseModel):
    role: Literal["user", "upper_user", "admin"]
