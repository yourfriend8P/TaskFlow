from fastapi import FastAPI, HTTPException, status, Query, Depends
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv
import os
from sqlalchemy.orm import Session
import models
from database import get_db, Base, engine
from sqlalchemy import select, or_
from schemas import (
    UserCreate,
    UserResponse,
    TokenResponse,
    UserLogin,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    TaskAssign,
)
from security import hash_password, verify_password

# from models import TaskDB
from datetime import datetime, timedelta, timezone
import jwt

# temporarily placed here
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
    created_by: models.User = Depends(get_current_user),
):

    task = db.scalar(
        select(models.Task).where(
            models.Task.id == task_id,
            or_(
                models.Task.created_by_id == created_by.id,
                models.Task.assigned_to_id == created_by.id,
            ),
        )
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    if task.created_by_id != created_by.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this task",
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
    # Save the previous status before applying changes
    old_status = task.status

    for field, value in update_data.items():
        setattr(task, field, value)

    # Record the update in the activity history
    activity = models.TaskActivity(
        task_id=task.id,
        actor_id=created_by.id,
        action="task_updated",
        old_status=old_status,
        new_status=task.status,
        details=f"Updated fields: {', '.join(update_data.keys())}",
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
    admin: models.User = Depends(require_admin),
):
    task = db.get(models.Task, task_id)

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

    task.assigned_to_id = assigned_user.id

    activity = models.TaskActivity(
        task_id=task.id,
        actor_id=admin.id,
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
    task = db.get(models.Task, task_id)

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
