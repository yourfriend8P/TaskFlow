import strawberry
from strawberry.types import Info


@strawberry.type
class Query:

    @strawberry.field
    def hello(self, info: Info) -> str:
        return "Hello from TaskFlow GraphQL!"


schema = strawberry.Schema(query=Query)
