from fastapi import FastAPI, HTTPException, status, Query, Depends
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv
import os
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func
import models
from database import get_db, Base, engine
from schemas import (
    UserCreate,
    UserResponse,
    TokenResponse,
    UserLogin,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    TaskAssign,
    UserStatusUpdate,
    UserRoleUpdate,
)
from security import hash_password, verify_password

# from models import TaskDB
from datetime import datetime, timedelta, timezone
import jwt

SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app = FastAPI(title="TaskFlow API")


## Dependency to get the current user from the token
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        user_id = payload.get("sub")

        if user_id is None:
            raise credentials_exception

        user_id = int(user_id)

    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    user = db.get(models.User, user_id)

    if user is None or not user.is_active:
        raise credentials_exception

    return user


# Dependency to require admin role
def require_admin(
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def require_normal_user(
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Normal user privileges required",
        )
    return current_user


def require_upper_user(
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role not in ["admin", "upper_user"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor privileges required",
        )
    return current_user


@app.get("/")
async def root():
    return {"message": "TaskFlow API is running", "message2": "Good day to you"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    from sqlalchemy import text

    db.execute(text("Select 1"))
    return {"status": "healthy", "database": "connected"}


# Register a new user
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    existing_user = db.scalar(
        select(models.User).where(models.User.email == user_data.email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = models.User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        role="user",
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    return user


# Login endpoint
@app.post("/auth/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(models.User).where(models.User.email == form_data.username))

    if user is None or not verify_password(
        form_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    token = jwt.encode(
        {"sub": str(user.id), "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }


# Read all tasks, with optional filters
@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    statement = (
        select(models.Task)
        .where(
            or_(
                models.Task.created_by_id == current_user.id,
                models.Task.assigned_to_id == current_user.id,
            )
        )
        .order_by(models.Task.id.desc())
    )

    return db.scalars(statement).all()


# # Count tasks
# @app.get("/tasks/count")
# def count_task(db: Session = Depends(get_db)):
#     return {"count": db.query(TaskDB).count()}


# Read one task
@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    task = db.scalar(
        select(models.Task).where(
            models.Task.id == task_id,
            or_(
                models.Task.created_by_id == current_user.id,
                models.Task.assigned_to_id == current_user.id,
            ),
        )
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


# Create a task
@app.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    task_data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):

    task = models.Task(
        title=task_data.title,
        description=task_data.description,
        priority=task_data.priority,
        due_date=task_data.due_date,
        created_by_id=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return task


# Update a task
@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):

    task = db.scalar(
        select(models.Task).where(
            models.Task.id == task_id,
            or_(
                models.Task.created_by_id == current_user.id,
                models.Task.assigned_to_id == current_user.id,
            ),
        )
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    update_data = task_data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    for field, value in update_data.items():
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be null",
            )

    # Assigned users can only change task status.
    if task.created_by_id != current_user.id:
        if current_user.role != "user" or set(update_data.keys()) != {"status"}:

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update the status of your assigned tasks",
            )

    # Save the previous status before applying changes
    old_status = task.status
    update_data = task_data.model_dump(exclude_unset=True)

    # Apply the requested changes.
    for field, value in update_data.items():
        setattr(task, field, value)

    # Record a specific action when the status changes.
    if "status" in update_data and old_status != task.status:
        action = "status_changed"
        details = (
            f"Status changed from {old_status} to {task.status}"
            f" updated fields: {', '.join(update_data.keys())}"
        )
    else:
        action = "task_updated"
        details = f"Updated fields: {', '.join(update_data.keys())}"

    activity = models.TaskActivity(
        task_id=task.id,
        actor_id=current_user.id,
        action=action,
        old_status=old_status,
        new_status=task.status,
        details=details,
    )

    db.add(activity)
    db.commit()
    db.refresh(task)

    return task


# Delete a task
@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.scalar(
        select(models.Task).where(
            models.Task.id == task_id,
            models.Task.created_by_id == get_current_user().id,
        )
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    db.delete(task)
    db.commit()

    return {"message": "Task deleted successfully"}


# Assign a task to a user
@app.patch(
    "/tasks/{task_id}/assign",
    response_model=TaskResponse,
)
def assign_task(
    task_id: int,
    assignment: TaskAssign,
    db: Session = Depends(get_db),
    supervisor: models.User = Depends(require_upper_user),
):
    task = db.scalar(
        select(models.Task).where(
            models.Task.id == task_id, models.Task.created_by_id == supervisor.id
        ),
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    assigned_user = db.get(models.User, assignment.assigned_to_id)

    if assigned_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assigned user not found",
        )
    # We can later change this to allow assigning tasks to upper users or admins if needed
    if assigned_user.role != "user":
        raise HTTPException(
            status_code=400,
            detail="Tasks can only be assigned to normal users",
        )

    task.assigned_to_id = assigned_user.id

    activity = models.TaskActivity(
        task_id=task.id,
        actor_id=supervisor.id,
        action="task assigned",
        details=f"Task assigned to user {assigned_user.id}",
    )
    db.add(activity)
    db.commit()
    db.refresh(task)

    return task


# Activity History endpoint
@app.get("/tasks/{task_id}/activities")
def get_task_activities(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Admins cannot access individual task histories.
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot access individual task activities",
        )

    task = db.scalar(
        select(models.Task).where(
            models.Task.id == task_id,
            or_(
                models.Task.created_by_id == current_user.id,
                models.Task.assigned_to_id == current_user.id,
            ),
        )
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    # Only the task creator, assignee, or an admin can view history
    if (
        task.created_by_id != current_user.id
        and task.assigned_to_id != current_user.id
        and current_user.role != "admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view this task's activity",
        )

    activities = (
        db.query(models.TaskActivity)
        .filter(models.TaskActivity.task_id == task_id)
        .order_by(models.TaskActivity.created_at.desc())
        .all()
    )

    return activities


# admin endpoints
@app.get("/admin/dashboard")
def admin_dashboard(
    db: Session = Depends(get_db), admin: models.User = Depends(require_admin)
):
    total_users = db.scalar(select(func.count(models.User.id)))

    active_users = db.scalar(
        select(func.count(models.User.id)).where(models.User.is_active == True)
    )

    total_tasks = db.scalar(select(func.count(models.Task.id)))

    status_result = db.execute(
        select(models.Task.status, func.count(models.Task.id)).group_by(
            models.Task.status
        )
    ).all()

    tasks_by_status = {
        "todo": 0,
        "in_progress": 0,
        "completed": 0,
    }

    for task_status, count in status_result:
        tasks_by_status[task_status] = count

    completed_tasks = tasks_by_status["completed"]

    completion_rate = (
        round((completed_tasks / total_tasks) * 100, 2) if total_tasks > 0 else 0.0
    )

    now = datetime.now(timezone.utc)

    overdue_tasks = db.scalar(
        select(func.count())
        .select_from(models.Task)  # ---> select count(*) from ...
        .where(models.Task.due_date < now, models.Task.status != "completed")
    )

    upcoming_tasks = db.scalar(
        select(func.count())
        .select_from(models.Task)
        .where(models.Task.due_date >= now, models.Task.status != "completed")
    )

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_tasks": total_tasks,
        "tasks_by_status": tasks_by_status,
        "overdue_tasks": overdue_tasks,
        "upcoming_tasks": upcoming_tasks,
        "completion_rate": completion_rate,
    }


# Admin: Get all users
@app.get("/admin/users")
def get_all_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    users = db.scalars(select(models.User).order_by(models.User.id)).all()

    return [
        {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
        }
        for user in users
    ]


@app.patch("/admin/users/{user_id}/status")
def deactivate_user(
    user_id: int,
    user_data: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = db.get(models.User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent admins from deactivating themselves
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot deactivate your own account",
        )

    if user.role == "admin" and user.is_active and not user_data.is_active:
        active_admins = db.scalar(
            select(func.count(models.User.id)).where(
                models.User.role == "admin",
                models.User.is_active == True,
            )
        )

    if active_admins <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate the last active administrator",
        )

    user.is_active = user_data.is_active

    db.commit()
    db.refresh(user)

    return {
        "message": "User status updated successfully",
        "user_id": user.id,
        "is_active": user.is_active,
    }


@app.patch("/admin/users/{user_id}/role")
def update_user_role(
    user_id: int,
    role_data: UserRoleUpdate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(models.User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent admins from changing their own role
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot change your own role",
        )

    # for now, we will not allow changing a user's role to admin through this endpoint
    if role_data.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot assign the admin role to any user",
        )

    old_role = user.role
    user.role = role_data.role

    db.commit()
    db.refresh(user)

    return {
        "message": "User role updated successfully",
        "user_id": user.id,
        "old_role": old_role,
        "new_role": user.role,
    }
