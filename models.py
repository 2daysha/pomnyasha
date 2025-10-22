from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    task_type: Optional[str] = None
    duration_minutes: Optional[int] = None
    priority: str = "medium"
    deadline: Optional[datetime] = None

class TaskCreate(TaskBase):
    user_id: int

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    task_type: Optional[str] = None
    duration_minutes: Optional[int] = None
    priority: Optional[str] = None
    deadline: Optional[datetime] = None

class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    task_id: int
    created_at: datetime
    user_id: int

class UserBase(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    created_at: datetime
    tasks: List[TaskResponse] = Field(default_factory=list)

class UserWithTasks(UserResponse):
    tasks: List[TaskResponse] = Field(default_factory=list)