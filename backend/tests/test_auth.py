from models import User
from security import hash_password


def test_register_user(client):
    response = client.post(
        "/auth/register",
        json={
            "name": "Test User",
            "email": "testuser@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "testuser@example.com"
    assert data["name"] == "Test User"
    assert data["role"] == "user"


def test_register_duplicate_email(client):
    user_data = {
        "name": "Duplicate User",
        "email": "duplicate@example.com",
        "password": "TestPassword123!",
    }

    first_response = client.post("/auth/register", json=user_data)
    second_response = client.post("/auth/register", json=user_data)

    assert first_response.status_code == 201
    assert second_response.status_code == 409

    assert second_response.json()["detail"] == (
        "An account with this email already exists."
    )


def test_login_success(client):
    client.post(
        "/auth/register",
        json={
            "name": "Login Test",
            "email": "login@example.com",
            "password": "password123",
        },
    )

    response = client.post(
        "/auth/login",
        data={
            "username": "login@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_login_wrong_password(client):
    client.post(
        "/auth/register",
        json={
            "name": "Wrong Password",
            "email": "wrongpass@example.com",
            "password": "password123",
        },
    )

    response = client.post(
        "/auth/login",
        data={
            "username": "wrongpass@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == 401


def test_login_unknown_email(client):
    response = client.post(
        "/auth/login",
        data={
            "username": "unknown@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 401


def test_tasks_without_token(client):
    response = client.get("/tasks")
    assert response.status_code == 401


def test_tasks_with_invalid_token(client):
    response = client.get(
        "/tasks",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


def test_tasks_with_valid_token(client):
    client.post(
        "/auth/register",
        json={
            "name": "Protected Test",
            "email": "protected@example.com",
            "password": "password123",
        },
    )

    login = client.post(
        "/auth/login",
        data={
            "username": "protected@example.com",
            "password": "password123",
        },
    )

    token = login.json()["access_token"]

    response = client.get(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200


def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200


def test_login_upgrades_bcrypt_to_argon2(client, db_session):
    # Register a user normally.
    client.post(
        "/auth/register",
        json={
            "name": "Legacy User",
            "email": "legacy@example.com",
            "password": "password123",
        },
    )

    # Replace the user's Argon2 hash with an old bcrypt hash.
    user = db_session.query(User).filter_by(email="legacy@example.com").first()

    from passlib.context import CryptContext

    bcrypt_context = CryptContext(schemes=["bcrypt"])
    user.password_hash = bcrypt_context.hash("password123")
    db_session.commit()

    # Login using the correct password.
    response = client.post(
        "/auth/login",
        data={
            "username": "legacy@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200

    # Confirm the stored hash has been upgraded to Argon2.
    db_session.refresh(user)
    assert user.password_hash.startswith("$argon2")
