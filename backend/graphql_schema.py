import strawberry
from strawberry.types import Info
from datetime import datetime
import models
from sqlalchemy import select
from schemas import TaskCreate, TaskUpdate, ProjectUpdate, ProjectCreate
from pydantic import ValidationError


@strawberry.type
class UserType:
    id: int
    name: str
    email: str
    role: str
    is_active: bool


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
class ProjectInput:
    name: str
    description: str = ""


@strawberry.input
class ProjectUpdateInput:
    name: str | None = strawberry.UNSET
    description: str | None = strawberry.UNSET


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
    def get_tasks(self, info: Info) -> list[TaskType]:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not authenticated")

        tasks = db.scalars(
            select(models.Task)
            .where(
                (models.Task.created_by_id == user.id)
                | (models.Task.assigned_to_id == user.id)
            )
            .order_by(models.Task.id.desc())
        ).all()

        return [
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
            )
            for task in tasks
        ]

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
    def get_projects(self, info: Info) -> list[ProjectType]:
        user = info.context["current_user"]
        db = info.context["db"]

        if user is None:
            raise Exception("Not Authenticated")

        if user.role == "admin":
            raise Exception("Admin cannot access individual projects")

        projects = db.scalars(
            select(models.Project)
            .where(models.Project.created_by_id == user.id)
            .order_by(models.Project.created_at.desc())
        ).all()

        return [
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
        ]

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


schema = strawberry.Schema(query=Query, mutation=Mutation)
