from multiprocessing.util import info
import strawberry
from strawberry.types import Info
from datetime import datetime, timezone
import models
from sqlalchemy import case, func, select, case
from schemas import TaskCreate, TaskUpdate, ProjectUpdate, ProjectCreate, UserRoleUpdate
from pydantic import ValidationError


@strawberry.type
class UserType:
    id: int
    name: str
    email: str
    role: str
    is_active: bool


@strawberry.input
class UserStatusInput:
    is_active: bool


@strawberry.input
class UserRoleInput:
    role: str


# ------------------task-------------------
@strawberry.type
class TaskType:
    id: int
    title: str
    description: str
    status: str
    priority: str
    due_date: datetime | None
    project_id: int | None
    created_by_id: int
    assigned_to_id: int | None
    created_at: datetime
    updated_at: datetime
    # relationships
    creator: UserType
    assigned_user: UserType | None
    project: "ProjectType | None"


@strawberry.input
class TaskInput:
    title: str
    description: str
    priority: str
    due_date: datetime | None = None
    project_id: int | None = None


@strawberry.input
class TaskUpdateInput:
    title: str | None = strawberry.UNSET
    description: str | None = strawberry.UNSET
    priority: str | None = strawberry.UNSET
    status: str | None = strawberry.UNSET
    project_id: int | None = strawberry.UNSET


@strawberry.input
class TaskAssignInput:
    assigned_to_id: int


@strawberry.type
class TaskActivityType:
    id: int
    task_id: int
    actor_id: int
    action: str
    old_status: str | None
    new_status: str | None
    details: str
    created_at: datetime


@strawberry.type
class TaskConnection:
    items: list[TaskType]
    total: int
    limit: int
    offset: int


# ------------------project-------------------
@strawberry.type
class ProjectType:
    id: int
    name: str
    description: str
    created_by_id: int
    created_at: datetime
    creator: UserType
    tasks: list["TaskType"]


@strawberry.input
class ProjectInput:
    name: str
    description: str = ""


@strawberry.input
class ProjectUpdateInput:
    name: str | None = strawberry.UNSET
    description: str | None = strawberry.UNSET


@strawberry.type
class TasksByStatusType:
    todo: int
    in_progress: int
    completed: int


@strawberry.type
class ProjectConnection:
    items: list[ProjectType]
    total: int
    limit: int
    offset: int


# ------------------admin dashboard-------------------
@strawberry.type
class AdminDashboardType:
    total_users: int
    active_users: int
    total_tasks: int
    tasks_by_status: TasksByStatusType
    overdue_tasks: int
    upcoming_tasks: int
    completion_rate: float


@strawberry.type
class AdminUserType:
    id: int
    name: str
    email: str
    role: str
    is_active: bool


@strawberry.type
class AdminUserConnection:
    items: list[AdminUserType]
    total: int
    limit: int
    offset: int


@strawberry.type
class Query:

    @strawberry.field
    def hello(self) -> str:
        return "Hello from taskflow GraphQL!"

    @strawberry.field
    def me(self, info: Info) -> UserType:
        user = info.context["current_user"]

        if user is None:
            raise Exception("Not authenticated")

        return UserType(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        )

    @strawberry.field
    def get_tasks(
        self,
        info: Info,
        limit: int = 10,
        offset: int = 0,
        project_id: int | None = None,
        task_status: str | None = None,
        priority: str | None = None,
        search: str | None = None,
        overdue: bool = False,
        due_before: datetime | None = None,
        sort_by: str = "newest",
    ) -> TaskConnection:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not authenticated")

        if user.role == "admin":
            raise Exception("Admin cannot access individual tasks")

        conditions = (models.Task.created_by_id == user.id) | (
            models.Task.assigned_to_id == user.id
        )
        # Validate pagination parameters
        if limit < 1 or limit > 100:
            raise Exception("Limit must be between 1 and 100")

        if offset < 0:
            raise Exception("Offset cannot be negative")

        if project_id is not None:
            conditions = conditions & (models.Task.project_id == project_id)

        if task_status is not None:
            if task_status not in ["todo", "in_progress", "completed"]:
                raise Exception("Invalid task status")
            conditions = conditions & (models.Task.status == task_status)

        if priority is not None:
            if priority not in ["low", "medium", "high"]:
                raise Exception("Invalid priority")
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

        sort_options = {
            "newest": models.Task.id.desc(),
            "oldest": models.Task.id.asc(),
            "priority_high": case(
                (models.Task.priority == "high", 1),
                (models.Task.priority == "medium", 2),
                (models.Task.priority == "low", 3),
            ),
            "priority_low": case(
                (models.Task.priority == "low", 1),
                (models.Task.priority == "medium", 2),
                (models.Task.priority == "high", 3),
            ),
            "due_date": models.Task.due_date.asc().nullslast(),
        }

        if sort_by not in sort_options:
            raise Exception("Invalid sorting option")

        total = db.scalar(select(func.count(models.Task.id)).where(conditions))

        statement = (
            select(models.Task)
            .where(conditions)
            .order_by(sort_options[sort_by])
            .offset(offset)
            .limit(limit)
        )
        tasks = db.scalars(statement).all()

        return TaskConnection(
            items=[
                TaskType(
                    id=task.id,
                    title=task.title,
                    description=task.description,
                    status=task.status,
                    priority=task.priority,
                    due_date=task.due_date,
                    project_id=task.project_id,
                    created_by_id=task.created_by_id,
                    assigned_to_id=task.assigned_to_id,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    # Relationships
                    creator=UserType(
                        id=task.creator.id,
                        name=task.creator.name,
                        email=task.creator.email,
                        role=task.creator.role,
                        is_active=task.creator.is_active,
                    ),
                    assigned_user=(
                        UserType(
                            id=task.assignee.id,
                            name=task.assignee.name,
                            email=task.assignee.email,
                            role=task.assignee.role,
                            is_active=task.assignee.is_active,
                        )
                        if task.assignee
                        else None
                    ),
                    project=(
                        ProjectType(
                            id=task.project.id,
                            name=task.project.name,
                            description=task.project.description,
                            created_by_id=task.project.created_by_id,
                            created_at=task.project.created_at,
                            creator=UserType(
                                id=task.project.creator.id,
                                name=task.project.creator.name,
                                email=task.project.creator.email,
                                role=task.project.creator.role,
                                is_active=task.project.creator.is_active,
                            ),
                            tasks=[],
                        )
                        if task.project
                        else None
                    ),
                )  # Keep all your existing TaskType fields here
                for task in tasks
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    @strawberry.field
    def get_task_by_id(self, info: Info, TaskId: int) -> TaskType:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not Authenticated")

        if user.role == "admin":
            raise Exception("Admin cannot access individual tasks")

        task = db.scalar(
            select(models.Task).where(
                (models.Task.id == TaskId),
                (
                    (models.Task.created_by_id == user.id)
                    | (models.Task.assigned_to_id == user.id)
                ),
            )
        )

        if task is None:
            raise Exception("Task not found")

        return TaskType(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            project_id=task.project_id,
            created_by_id=task.created_by_id,
            assigned_to_id=task.assigned_to_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @strawberry.field
    def get_projects(
        self,
        info: Info,
        limit: int = 10,
        offset: int = 0,
        search: str | None = None,
        sort_by: str = "newest",
    ) -> ProjectConnection:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not Authenticated")

        if user.role == "admin":
            raise Exception("Admin cannot access individual projects")

        if search is not None:
            search = search.strip()

        # Validate pagination parameters
        if limit < 1 or limit > 100:
            raise Exception("Limit must be between 1 and 100")

        if offset < 0:
            raise Exception("Offset cannot be negative")

        # project filter options
        sort_options = {
            "newest": models.Project.id.desc(),
            "oldest": models.Project.id.asc(),
            "name_asc": models.Project.name.asc(),
            "name_desc": models.Project.name.desc(),
        }
        if sort_by not in sort_options:
            raise Exception("Invalid sorting option")

        statement = select(models.Project).where(
            models.Project.created_by_id == user.id
        )

        if search:
            statement = statement.where(models.Project.name.ilike(f"%{search}%"))

        total = db.scalar(
            select(func.count(models.Project.id))
            .where(models.Project.created_by_id == user.id)
            .where(models.Project.name.ilike(f"%{search}%"))
            if search
            else select(func.count(models.Project.id)).where(
                models.Project.created_by_id == user.id
            )
        )

        projects = db.scalars(
            statement.order_by(sort_options[sort_by]).limit(limit).offset(offset)
        ).all()

        return ProjectConnection(
            items=[
                ProjectType(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    created_by_id=project.created_by_id,
                    created_at=project.created_at,
                    creator=project.creator,
                    tasks=project.tasks,
                )
                for project in projects
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    @strawberry.field
    def get_projects_by_id(self, info: Info, project_id: int) -> ProjectType:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("User not authenticated")

        if user.role == "admin":
            raise Exception("Admin cannot access individual projects")

        project = db.scalar(
            select(models.Project).where(
                models.Project.id == project_id,
                models.Project.created_by_id == user.id,
            )
        )

        if project is None:
            raise Exception("Project not found")

        return ProjectType(
            id=project.id,
            name=project.name,
            description=project.description,
            created_by_id=project.created_by_id,
            created_at=project.created_at,
            creator=project.creator,
            tasks=project.tasks,
        )

    @strawberry.field
    def get_task_activities(
        self, info: Info, task_id: int, sort_by: str = "newest"
    ) -> list[TaskActivityType]:

        user = info.context["current_user"]
        db = info.context["db"]

        # Check authentication
        if user is None:
            raise Exception("Not authenticated")

        # Admin cannot access individual task activities
        if user.role == "admin":
            raise Exception("Admin cannot access individual task activities")

        sort_options = {
            "newest": models.TaskActivity.created_at.desc(),
            "oldest": models.TaskActivity.created_at.asc(),
        }
        if sort_by not in sort_options:
            raise Exception("Invalid sorting option")
        # Check if the task exists and belongs to the user (creator or assigned to)
        task = db.scalar(
            select(models.Task).where(
                models.Task.id == task_id,
                (
                    (models.Task.created_by_id == user.id)
                    | (models.Task.assigned_to_id == user.id)
                ),
            )
        )

        if task is None:
            raise Exception("Task not found")

        # Retrieve task activities, newest first
        activities = db.scalars(
            select(models.TaskActivity)
            .filter(models.TaskActivity.task_id == task_id)
            .order_by(sort_options[sort_by])
        ).all()

        return [
            TaskActivityType(
                id=activity.id,
                task_id=activity.task_id,
                actor_id=activity.actor_id,
                action=activity.action,
                old_status=activity.old_status,
                new_status=activity.new_status,
                details=activity.details,
                created_at=activity.created_at,
            )
            for activity in activities
        ]

    @strawberry.field
    def admin_dashboard(self, info: Info) -> AdminDashboardType:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not authenticated")

        if user.role != "admin":
            raise Exception("Only admin can access the dashboard")

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

        overdue_tasks = db.scalar(
            select(func.count(models.Task.id)).where(
                models.Task.due_date < datetime.utcnow(),
                models.Task.status != "completed",
            )
        )
        upcoming_tasks = db.scalar(
            select(func.count(models.Task.id)).where(
                models.Task.due_date >= datetime.utcnow(),
                models.Task.status != "completed",
            )
        )
        completed_tasks = db.scalar(
            select(func.count(models.Task.id)).where(models.Task.status == "completed")
        )

        completion_rate = (
            (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0
        )

        return AdminDashboardType(
            total_users=total_users,
            active_users=active_users,
            total_tasks=total_tasks,
            tasks_by_status=TasksByStatusType(
                todo=tasks_by_status["todo"],
                in_progress=tasks_by_status["in_progress"],
                completed=tasks_by_status["completed"],
            ),
            overdue_tasks=overdue_tasks,
            upcoming_tasks=upcoming_tasks,
            completion_rate=completion_rate,
        )

    @strawberry.field
    def all_users(
        self,
        info: Info,
        sort_by: str = "id",
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> AdminUserConnection:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not authenticated")

        if user.role != "admin":
            raise Exception("Only admins can access all users")

        # Validate pagination
        if limit < 1 or limit > 100:
            raise Exception("Limit must be between 1 and 100")

        if offset < 0:
            raise Exception("Offset cannot be negative")

        sort_options = {
            "id": models.User.id.asc(),
            "name": models.User.name.asc(),
            "email": models.User.email.asc(),
            "role": models.User.role.asc(),
            "is_active": models.User.is_active.desc(),
            "inactive": models.User.is_active.asc(),
        }
        if sort_by not in sort_options:
            raise Exception("Invalid sorting option")

        # Build the base query
        conditions = []

        # Search by name or email
        if search is not None:
            search = search.strip()

            if search:
                conditions.append(
                    (models.User.name.ilike(f"%{search}%"))
                    | (models.User.email.ilike(f"%{search}%"))
                )

        # Filter by role
        if role is not None:
            if role not in ["user", "upper", "admin"]:
                raise Exception("Invalid user role")

            conditions.append(models.User.role == role)

        # Filter by active status
        if is_active is not None:
            conditions.append(models.User.is_active == is_active)

        # Preserve existing sorting behavior
        if sort_by == "inactive":
            conditions.append(models.User.is_active.is_(False))

        elif sort_by == "is_active":
            conditions.append(models.User.is_active.is_(True))

        # Apply filters
        stmt = select(models.User)

        if conditions:
            stmt = stmt.where(*conditions)

        # Count all matching users before pagination
        total = (
            db.scalar(
                select(func.count(models.User.id))
                .select_from(models.User)
                .where(*conditions)
            )
            if conditions
            else db.scalar(select(func.count(models.User.id)))
        )

        # Retrieve paginated users
        users = db.scalars(
            stmt.order_by(sort_options[sort_by]).limit(limit).offset(offset)
        ).all()

        # Return users with pagination metadata
        return AdminUserConnection(
            items=[
                AdminUserType(
                    id=admin_user.id,
                    name=admin_user.name,
                    email=admin_user.email,
                    role=admin_user.role,
                    is_active=admin_user.is_active,
                )
                for admin_user in users
            ],
            total=total or 0,
            limit=limit,
            offset=offset,
        )


@strawberry.type
class Mutation:

    @strawberry.mutation
    def create_task(self, info: Info, task_data: TaskInput) -> TaskType:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not Authenticated")

        if user.role == "admin":
            raise Exception("Admin cannot create task")

        try:
            validated_data = TaskCreate(
                title=task_data.title,
                description=task_data.description,
                priority=task_data.priority,
                due_date=task_data.due_date,
                project_id=task_data.project_id,
            )
        except ValidationError as e:
            raise Exception(str(e))

        if validated_data.project_id is not None:
            project = db.scalars(
                select(models.Project).where(
                    models.Project.id == validated_data.project_id,
                    models.Project.created_by_id == user.id,
                )
            )
            if project is None:
                raise Exception("Project not found")

        task = models.Task(
            title=task_data.title,
            description=task_data.description,
            priority=task_data.priority,
            due_date=task_data.due_date,
            created_by_id=user.id,
            project_id=task_data.project_id,
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        return TaskType(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            project_id=task.project_id,
            created_by_id=task.created_by_id,
            assigned_to_id=task.assigned_to_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            creator=UserType(
                id=user.id,
                name=user.name,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
            ),
            assigned_user=(
                UserType(
                    id=task.assignee.id,
                    name=task.assignee.name,
                    email=task.assignee.email,
                    role=task.assignee.role,
                    is_active=task.assignee.is_active,
                )
                if task.assignee
                else None
            ),
            project=(
                ProjectType(
                    id=task.project.id,
                    name=task.project.name,
                    description=task.project.description,
                    created_by_id=task.project.created_by_id,
                    created_at=task.project.created_at,
                    creator=UserType(
                        id=task.project.creator.id,
                        name=task.project.creator.name,
                        email=task.project.creator.email,
                        role=task.project.creator.role,
                        is_active=task.project.creator.is_active,
                    ),
                    tasks=[],
                )
                if task.project
                else None
            ),
        )

    @strawberry.mutation
    def update_task(self, info: Info, task_id: int, input: TaskUpdateInput) -> TaskType:

        user = info.context["current_user"]
        db = info.context["db"]

        # 1. Authentication check
        if user is None:
            raise Exception("Not authenticated")

        # 2. Admin permission check
        if user.role == "admin":
            raise Exception("Admin cannot update individual tasks")

        # 3. Find the task (creator or assignee only)

        task = db.scalar(
            select(models.Task).where(
                (models.Task.id == task_id),
                (
                    (models.Task.created_by_id == user.id)
                    | (models.Task.assigned_to_id == user.id)
                ),
            )
        )

        if task is None:
            raise Exception("Task not found")

        # 4. Collect only fields supplied by the client
        update_data = {}

        for field in [
            "title",
            "description",
            "priority",
            "status",
            "project_id",
        ]:
            value = getattr(input, field)

            if value is not strawberry.UNSET:
                update_data[field] = value

        if not update_data:
            raise Exception("Provide at least one field to update")

        # 5. Assigned users can only change status
        if task.created_by_id != user.id:
            if user.role != "user" or set(update_data.keys()) != {"status"}:
                raise Exception("You can only update the status of your assigned tasks")

        # 6. Validate Fields

        try:
            validate_data = TaskUpdate.model_validate(update_data)
        except ValidationError as e:
            raise Exception(str(e))

        update_data = validate_data.model_dump(exclude_unset=True)

        # 7. Validate destination project ownership
        if "project_id" in update_data and update_data["project_id"] is not None:
            project = db.scalar(
                select(models.Project).where(
                    models.Project.id == update_data["project_id"],
                    models.Project.created_by_id == user.id,
                )
            )

            if project is None:
                raise Exception("Project not found")

        # 8. Save previous status
        old_status = task.status

        # 9. Apply updates
        for field, value in update_data.items():
            setattr(task, field, value)

        # 10. Create activity record
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
            actor_id=user.id,
            action=action,
            old_status=old_status,
            new_status=task.status,
            details=details,
        )

        db.add(activity)
        db.commit()
        db.refresh(task)

        # 11. Return GraphQL TaskType
        return TaskType(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            project_id=task.project_id,
            created_by_id=task.created_by_id,
            assigned_to_id=task.assigned_to_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @strawberry.mutation
    def delete_task(self, info: Info, task_id: int) -> bool:
        user = info.context["current_user"]
        db = info.context["db"]

        # Check authentication
        if user is None:
            raise Exception("Not authenticated")

        # Admin cannot delete individual tasks
        if user.role == "admin":
            raise Exception("Admin cannot delete individual task")

        # Find a task created by the current user
        task = db.scalar(
            select(models.Task).where(
                models.Task.id == task_id,
                models.Task.created_by_id == user.id,
            )
        )

        if task is None:
            raise Exception("Task not found")

        # Delete Task
        db.delete(task)
        db.commit()

        return True

    @strawberry.mutation
    def create_project(self, info: Info, project_data: ProjectInput) -> ProjectType:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("User not Authenticated")

        if user.role == "admin":
            raise Exception("Admin cannot create projects")

        try:
            validated_data = ProjectCreate(
                name=project_data.name,
                description=project_data.description,
            )
        except ValidationError as e:
            raise Exception(str(e))

        project = models.Project(
            name=validated_data.name,
            description=validated_data.description,
            created_by_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        return ProjectType(
            id=project.id,
            name=project.name,
            description=project.description,
            created_by_id=project.created_by_id,
            created_at=project.created_at,
            creator=project.creator,
            tasks=project.tasks,
        )

    @strawberry.mutation
    def update_project(
        self, info: Info, projectID: int, project_data: ProjectUpdateInput
    ) -> ProjectType:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not authenticated")

        if user.role == "admin":
            raise Exception("Admin cannot update individual project")

        project = db.scalar(
            select(models.Project).where(
                models.Project.id == projectID, models.Project.created_by_id == user.id
            )
        )

        if project is None:
            raise Exception("Project not found")

        update_data = {}

        for field in [
            "name",
            "description",
        ]:
            value = getattr(project_data, field)

            if value is not strawberry.UNSET:
                update_data[field] = value

        if not update_data:
            raise Exception("Provide at least one field to update")

        try:
            validate_data = ProjectUpdate.model_validate(update_data)
        except ValidationError as e:
            raise Exception(str(e))

        update_data = validate_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if value is None:
                raise Exception(f"{field} cannot be null")

            setattr(project, field, value)

        db.commit()
        db.refresh(project)

        return ProjectType(
            id=project.id,
            name=project.name,
            description=project.description,
            created_by_id=project.created_by_id,
            created_at=project.created_at,
            creator=project.creator,
            tasks=project.tasks,
        )

    @strawberry.mutation
    def delete_project(self, info: Info, project_id: int) -> bool:
        user = info.context["current_user"]
        db = info.context["db"]

        # Check authentication
        if user is None:
            raise Exception("Not authenticated")

        # Admin cannot delete individual project
        if user.role == "admin":
            raise Exception("Admin cannot delete individual project")

        # Find a project created by the current user
        project = db.scalar(
            select(models.Project).where(
                models.Project.id == project_id,
                models.Project.created_by_id == user.id,
            )
        )

        if project is None:
            raise Exception("Project not found")

        for task in project.tasks:
            task.project_id = None

        # Delete Project
        db.delete(project)
        db.commit()

        return True

    @strawberry.mutation
    def task_assign(
        self, info: Info, task_id: int, assign_data: TaskAssignInput
    ) -> TaskType:
        user = info.context["current_user"]
        db = info.context["db"]

        # Check authentication
        if user is None:
            raise Exception("Not authenticated")

        # Only supervisors can assign tasks
        if user.role != "upper_user":
            raise Exception("Only supervisors can assign tasks")

        task = db.scalar(
            select(models.Task).where(
                models.Task.id == task_id, models.Task.created_by_id == user.id
            )
        )

        if task is None:
            raise Exception("Task not found")

        # Find the user receiving the task
        assigned_user = db.scalar(
            select(models.User).where(models.User.id == assign_data.assigned_to_id)
        )

        if assigned_user is None:
            raise Exception("Assigned user not found")

        # Only normal users can receive tasks
        if assigned_user.role != "user":
            raise Exception("Tasks can only be assigned to normal users")

        # Assign the task
        task.assigned_to_id = assign_data.assigned_to_id

        # Record activity
        activity = models.TaskActivity(
            task_id=task.id,
            actor_id=user.id,
            action="task assigned",
            details=f"Task assigned to user {assigned_user.id}",
        )

        db.add(activity)
        db.commit()
        db.refresh(task)

        return TaskType(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            project_id=task.project_id,
            created_by_id=task.created_by_id,
            assigned_to_id=task.assigned_to_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @strawberry.mutation
    def update_user_status(
        self, info: Info, user_id: int, status_data: UserStatusInput
    ) -> AdminUserType:
        user = info.context["current_user"]
        db = info.context["db"]

        # Check authentication
        if user is None:
            raise Exception("Not authenticated")

        # Only admins can update user status
        if user.role != "admin":
            raise Exception("Only admins can update user status")

        target_user = db.scalar(select(models.User).where(models.User.id == user_id))

        # Check if the target user is the same as the current user
        if target_user.id == user.id:
            raise Exception("You cannot deactivate your own account")

        # Check if the target user is an admin
        if target_user.role == "admin":
            raise Exception("Admins cannot deactivate other admins")

        target_user = db.scalar(select(models.User).where(models.User.id == user_id))

        if target_user is None:
            raise Exception("User not found")

        target_user.is_active = status_data.is_active

        db.commit()
        db.refresh(target_user)

        return AdminUserType(
            id=target_user.id,
            name=target_user.name,
            email=target_user.email,
            role=target_user.role,
            is_active=target_user.is_active,
        )

    @strawberry.mutation
    def update_user_role(
        self, info: Info, user_id: int, role_data: UserRoleInput
    ) -> AdminUserType:
        user = info.context["current_user"]
        db = info.context["db"]

        # Check authentication
        if user is None:
            raise Exception("Not authenticated")

        # Only admins can update user roles
        if user.role != "admin":
            raise Exception("Only admins can update user roles")

        target_user = db.scalar(select(models.User).where(models.User.id == user_id))

        if target_user is None:
            raise Exception("User not found")

        # Check if the target user is the same as the current user
        if target_user.id == user.id:
            raise Exception("You cannot change your own role")

        # Check if the target user is an admin
        if target_user.role == "admin":
            raise Exception("Admins cannot change the role of other admins")

        # for now, we will not allow changing a user's role to admin through this endpoint
        if role_data.role == "admin":
            raise Exception(
                "You cannot assign the admin role to any user",
            )

        try:
            validated_role = UserRoleUpdate(role=role_data.role)
        except ValueError as e:
            raise Exception(str(e))

        target_user.role = validated_role.role

        db.commit()
        db.refresh(target_user)

        return AdminUserType(
            id=target_user.id,
            name=target_user.name,
            email=target_user.email,
            role=target_user.role,
            is_active=target_user.is_active,
        )


schema = strawberry.Schema(query=Query, mutation=Mutation)
