from fastapi import FastAPI, HTTPException, status, Query, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
import os
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func
import models
from database import get_db
from schemas import (
    UserCreate,
    UserResponse,
    TokenResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    TaskAssign,
    UserStatusUpdate,
    UserRoleUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from security import hash_password, verify_password, verify_password_and_update
from datetime import datetime, timedelta, timezone
import jwt
from strawberry.fastapi import GraphQLRouter
from graphql_schema import schema

SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app = FastAPI(title="TaskFlow API")

graphql_app = GraphQLRouter(schema)

app.include_router(graphql_app, prefix="/graphql")


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
    if current_user.role not in ["upper_user"]:
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


# ------------------------------------------------------------Login Endpoints----------------------------------------------------------
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

    is_valid, updated_hash = verify_password_and_update(
        form_data.password,
        user.password_hash,
    )

    if not is_valid:
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

    if updated_hash is not None:
        user.password_hash = updated_hash
        db.commit()

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


# ------------------------------------------------------------Task Endpoints----------------------------------------------------------
# Read all tasks, with optional filters
@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    project_id: int | None = None,
    task_status: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    overdue: bool = False,
    due_before: datetime | None = None,
    skip: int = Query(
        default=0, ge=0
    ),  # for pagination and used query to prevent -ve number
    limit: int = Query(
        default=20, ge=1, le=100
    ),  # for pagination and used query to prevent -ve number
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot access individual task records",
        )

    conditions = (models.Task.created_by_id == current_user.id) | (
        models.Task.assigned_to_id == current_user.id
    )

    if project_id is not None:
        conditions = conditions & (models.Task.project_id == project_id)

    if task_status is not None:
        if task_status not in ["todo", "in_progress", "completed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid task status",
            )
        conditions = conditions & (models.Task.status == task_status)

    if priority is not None:
        if priority not in ["low", "medium", "high"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task priority"
            )
        conditions = conditions & (models.Task.priority == priority)

    if search is not None:
        search = search.strip()

        if search:
            conditions = conditions & (models.Task.title.ilike(f"%{search}%"))

    if overdue:
        conditions = conditions & (
            (models.Task.due_date.is_not(None))
            & (models.Task.due_date < datetime.now(timezone.utc))
            & (models.Task.status != "completed")
        )

    if due_before is not None:
        conditions = conditions & (models.Task.due_date <= due_before)

    statement = (
        select(models.Task)
        .where(conditions)
        .order_by(models.Task.id.desc())
        .offset(skip)
        .limit(limit)
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
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot access individual tasks",
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
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin cannot create task"
        )

    if task_data.project_id is not None:
        project = db.scalar(
            select(models.Project).where(
                models.Project.id == task_data.project_id,
                models.Project.created_by_id == current_user.id,
            )
        )

        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )

    task = models.Task(
        title=task_data.title,
        description=task_data.description,
        priority=task_data.priority,
        due_date=task_data.due_date,
        created_by_id=current_user.id,
        project_id=task_data.project_id,
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

    # Admins cannot access individual task records.
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot update individual tasks",
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    update_data = task_data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    # Assigned users can only change task status.
    if task.created_by_id != current_user.id:
        if current_user.role != "user" or set(update_data.keys()) != {"status"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update the status of your assigned tasks",
            )

    # Validate destination project ownership
    if "project_id" in update_data and update_data["project_id"] is not None:
        project = db.scalar(
            select(models.Project).where(
                models.Project.id == update_data["project_id"],
                models.Project.created_by_id == current_user.id,
            )
        )

        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

    # Validate fields, allowing project_id to be None.
    for field, value in update_data.items():
        if value is None and field != "project_id":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be null",
            )

    # Save the previous status before applying changes
    old_status = task.status

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
def delete_task(
    task_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin cannot delete individual task",
        )

    task = db.scalar(
        select(models.Task).where(
            models.Task.id == task_id,
            models.Task.created_by_id == current_user.id,
        )
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    db.delete(task)
    db.commit()

    return Response(status_code=204)


# Assign a task to a user
@app.patch(
    "/tasks/{task_id}/assign",
    response_model=TaskResponse,
)
def assign_task(
    task_id: int,
    assignment: TaskAssign,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    supervisor: models.User = Depends(require_upper_user),
):
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admins cannot assign task"
        )

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

    activities = (
        db.query(models.TaskActivity)
        .filter(models.TaskActivity.task_id == task_id)
        .order_by(models.TaskActivity.created_at.desc())
        .all()
    )

    return activities


# ----------------------------------------------------------- admin endpoints ------------------------------------------------------
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

    if user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin cannot deactivate other admins",
        )

        # if active_admins <= 1:
        #     raise HTTPException(
        #         status_code=status.HTTP_400_BAD_REQUEST,
        #         detail="Cannot deactivate the last active administrator",
        #     )

    # Prevent admins from deactivating themselves
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot deactivate your own account",
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


# ----------------------------------------------- Project Endpoints -----------------------------------------------------------------


# Create a new project
@app.post(
    "/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED
)
def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot create a project",
        )
    project = models.Project(
        name=project_data.name,
        description=project_data.description,
        created_by_id=current_user.id,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


# Get all projects created by the current user
@app.get("/projects", response_model=list[ProjectResponse])
def get_projects(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot access project data",
        )
    projects = db.scalars(
        select(models.Project)
        .where(models.Project.created_by_id == current_user.id)
        .order_by(models.Project.created_at.desc())
    ).all()

    # if projects is None:
    #     raise HTTPException(
    #         status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
    #     )
    return projects


# Get project by project id
@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project_by_id(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot access individual projects",
        )
    project = db.scalar(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.created_by_id == current_user.id,
        )
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


# Update a project
@app.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    project_data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot edit individual projects",
        )

    project = db.scalar(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.created_by_id == current_user.id,
        )
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    update_data = project_data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    for field, value in update_data.items():
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{field} cannot be null",
            )

        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    return project


# Delete a project
@app.delete("/projects/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin cannot delete individual projects",
        )

    project = db.scalar(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.created_by_id == current_user.id,
        )
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    for task in project.tasks:
        task.project_id = None

    db.delete(project)
    db.commit()

    return {"message": "Project deleted successfully"}


# endpoint to view project tasks
@app.get("/projects/{project_id}/tasks", response_model=list[TaskResponse])
def get_project_tasks(
    project_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin cannot access individual project task",
        )
    project = db.scalar(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.created_by_id == current_user.id,
        )
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    task = db.scalars(
        select(models.Task)
        .where(models.Task.project_id == project_id)
        .order_by(models.Task.id.desc())
    ).all()

    return task
