import strawberry
from strawberry.types import Info


@strawberry.type
class UserType:
    id: int
    name: str
    email: str
    role: str
    is_active: bool


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


schema = strawberry.Schema(query=Query)
