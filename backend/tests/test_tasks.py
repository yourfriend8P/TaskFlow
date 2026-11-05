def test_create_task(client):
    client.post(
        "/auth/register",
        json={
            "name": "Task Creator",
            "email": "creator@example.com",
            "password": "password123",
        },
    )

    login = client.post(
        "/auth/login",
        data={
            "username": "creator@example.com",
            "password": "password123",
        },
    )

    token = login.json()["access_token"]

    response = client.post(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Complete TaskFlow testing",
            "description": "Test task creation endpoint",
            "priority": "high",
        },
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Complete TaskFlow testing"
    assert response.json()["priority"] == "high"
    assert response.json()["status"] == "todo"


def test_create_task_invalid_title(client):
    # Register and log in
    client.post(
        "/auth/register",
        json={
            "name": "Title Test",
            "email": "title@example.com",
            "password": "password123",
        },
    )

    login = client.post(
        "/auth/login",
        data={
            "username": "title@example.com",
            "password": "password123",
        },
    )

    token = login.json()["access_token"]

    response = client.post(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "AB",
            "description": "Invalid title",
            "priority": "medium",
        },
    )

    assert response.status_code == 422


def test_create_task_invalid_priority(client):
    client.post(
        "/auth/register",
        json={
            "name": "Priority Test",
            "email": "priority@example.com",
            "password": "password123",
        },
    )

    login = client.post(
        "/auth/login",
        data={
            "username": "priority@example.com",
            "password": "password123",
        },
    )

    token = login.json()["access_token"]

    response = client.post(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Valid task title",
            "description": "Invalid priority",
            "priority": "urgent",
        },
    )

    assert response.status_code == 422


def register_and_login(client, name, email):
    client.post(
        "/auth/register",
        json={
            "name": name,
            "email": email,
            "password": "password123",
        },
    )

    login = client.post(
        "/auth/login",
        data={
            "username": email,
            "password": "password123",
        },
    )

    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_user_sees_only_own_tasks(client):
    user1_headers = register_and_login(client, "User One", "userone@example.com")

    user2_headers = register_and_login(client, "User Two", "usertwo@example.com")

    client.post(
        "/tasks",
        headers=user1_headers,
        json={
            "title": "User One Task",
            "description": "",
            "priority": "medium",
        },
    )

    client.post(
        "/tasks",
        headers=user2_headers,
        json={
            "title": "User Two Task",
            "description": "",
            "priority": "medium",
        },
    )

    response = client.get("/tasks", headers=user1_headers)

    assert response.status_code == 200

    titles = [task["title"] for task in response.json()]

    assert "User One Task" in titles
    assert "User Two Task" not in titles


def test_user_cannot_access_other_users_task(client):
    user1_headers = register_and_login(client, "Owner", "owner@example.com")

    user2_headers = register_and_login(client, "Outsider", "outsider@example.com")

    task = client.post(
        "/tasks",
        headers=user1_headers,
        json={
            "title": "Private Task",
            "description": "",
            "priority": "high",
        },
    )

    task_id = task.json()["id"]

    response = client.get(
        f"/tasks/{task_id}",
        headers=user2_headers,
    )

    assert response.status_code == 404


def test_creator_can_update_task(client):
    headers = register_and_login(client, "Update Creator", "updatecreator@example.com")

    task = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Original Task",
            "description": "Original description",
            "priority": "low",
        },
    )

    task_id = task.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}",
        headers=headers,
        json={
            "title": "Updated Task",
            "description": "Updated description",
            "priority": "high",
        },
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Task"
    assert response.json()["description"] == "Updated description"
    assert response.json()["priority"] == "high"


def test_update_task_with_empty_body(client):
    headers = register_and_login(client, "Empty Update", "emptyupdate@example.com")

    task = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Task to Update",
            "description": "",
            "priority": "medium",
        },
    )

    response = client.patch(
        f"/tasks/{task.json()['id']}",
        headers=headers,
        json={},
    )

    assert response.status_code == 400


def test_update_task_with_null_title(client):
    headers = register_and_login(client, "Null Update", "nullupdate@example.com")

    task = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Task to Update",
            "description": "",
            "priority": "medium",
        },
    )

    response = client.patch(
        f"/tasks/{task.json()['id']}",
        headers=headers,
        json={"title": None},
    )

    assert response.status_code == 422


def test_supervisor_can_assign_task_to_user(client, db_session):
    supervisor_headers = register_and_login(
        client, "Supervisor", "supervisor@example.com"
    )

    employee_headers = register_and_login(client, "Employee", "employee@example.com")

    # Change supervisor's role in the test database
    from models import User

    supervisor = (
        db_session.query(User).filter_by(email="supervisor@example.com").first()
    )

    supervisor.role = "upper_user"
    db_session.commit()

    employee = db_session.query(User).filter_by(email="employee@example.com").first()

    task = client.post(
        "/tasks",
        headers=supervisor_headers,
        json={
            "title": "Assigned Task",
            "description": "Task assigned by supervisor",
            "priority": "high",
        },
    )

    task_id = task.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}/assign",
        headers=supervisor_headers,
        json={"assigned_to_id": employee.id},
    )

    assert response.status_code == 200


def test_assigned_user_can_change_status_only(client, db_session):
    supervisor_headers = register_and_login(
        client, "Supervisor Two", "supervisor2@example.com"
    )

    employee_headers = register_and_login(
        client, "Employee Two", "employee2@example.com"
    )

    from models import User

    supervisor = (
        db_session.query(User).filter_by(email="supervisor2@example.com").first()
    )

    supervisor.role = "upper_user"
    db_session.commit()

    employee = db_session.query(User).filter_by(email="employee2@example.com").first()

    task = client.post(
        "/tasks",
        headers=supervisor_headers,
        json={
            "title": "Employee Task",
            "description": "Assigned task",
            "priority": "medium",
        },
    )

    task_id = task.json()["id"]

    assignment = client.patch(
        f"/tasks/{task_id}/assign",
        headers=supervisor_headers,
        json={"assigned_to_id": employee.id},
    )

    assert assignment.status_code == 200

    # Employee can change status
    status_response = client.patch(
        f"/tasks/{task_id}",
        headers=employee_headers,
        json={"status": "in_progress"},
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "in_progress"

    # Employee cannot change title
    title_response = client.patch(
        f"/tasks/{task_id}",
        headers=employee_headers,
        json={"title": "Unauthorized Change"},
    )

    assert title_response.status_code == 403


def test_filter_tasks_by_status(client):
    headers = register_and_login(client, "Filter User", "filteruser@example.com")

    task = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Status Filter Task",
            "description": "",
            "priority": "medium",
        },
    )

    client.patch(
        f"/tasks/{task.json()['id']}",
        headers=headers,
        json={"status": "in_progress"},
    )

    response = client.get(
        "/tasks?task_status=in_progress",
        headers=headers,
    )

    assert response.status_code == 200
    assert all(t["status"] == "in_progress" for t in response.json())


def test_filter_tasks_by_priority(client):
    headers = register_and_login(
        client, "Priority Filter", "priorityfilter@example.com"
    )

    client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "High Priority Task",
            "description": "",
            "priority": "high",
        },
    )

    response = client.get(
        "/tasks?priority=high",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert all(t["priority"] == "high" for t in response.json())


def test_search_tasks(client):
    headers = register_and_login(client, "Search User", "searchuser@example.com")

    client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Prepare Documentation",
            "description": "Write project documentation",
            "priority": "medium",
        },
    )

    response = client.get(
        "/tasks?search=Documentation",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Prepare Documentation"


def test_task_pagination(client):
    headers = register_and_login(client, "Pagination User", "pagination@example.com")

    for i in range(5):
        client.post(
            "/tasks",
            headers=headers,
            json={
                "title": f"Pagination Task {i}",
                "description": "",
                "priority": "medium",
            },
        )

    response = client.get(
        "/tasks?skip=0&limit=2",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_task_status_change_creates_activity(client):
    headers = register_and_login(client, "Activity User", "activity@example.com")

    task = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Activity Test Task",
            "description": "",
            "priority": "medium",
        },
    )

    task_id = task.json()["id"]

    client.patch(
        f"/tasks/{task_id}",
        headers=headers,
        json={"status": "in_progress"},
    )

    response = client.get(
        f"/tasks/{task_id}/activities",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) >= 1

    activity = response.json()[0]

    assert activity["old_status"] == "todo"
    assert activity["new_status"] == "in_progress"


def test_outsider_cannot_view_task_activity(client):
    owner_headers = register_and_login(
        client, "Activity Owner", "activityowner@example.com"
    )

    outsider_headers = register_and_login(
        client, "Activity Outsider", "activityoutsider@example.com"
    )

    task = client.post(
        "/tasks",
        headers=owner_headers,
        json={
            "title": "Private Activity Task",
            "description": "",
            "priority": "low",
        },
    )

    response = client.get(
        f"/tasks/{task.json()['id']}/activities",
        headers=outsider_headers,
    )

    assert response.status_code == 404


def test_user_can_delete_own_task(client):
    user_headers = register_and_login(
        client, "Task Owner", "delete_own_task@example.com"
    )

    task_response = client.post(
        "/tasks",
        json={
            "title": "Task to delete",
            "priority": "medium",
        },
        headers=user_headers,
    )

    assert task_response.status_code == 201

    task_id = task_response.json()["id"]

    response = client.delete(
        f"/tasks/{task_id}",
        headers=user_headers,
    )

    assert response.status_code == 204


def test_update_task_with_invalid_status(client):
    headers = register_and_login(client, "Test User", "invalid_status@example.com")

    task_response = client.post(
        "/tasks",
        json={"title": "Test task", "priority": "medium"},
        headers=headers,
    )
    task_id = task_response.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}",
        json={"status": "invalid_status"},
        headers=headers,
    )

    assert response.status_code == 422


def test_update_task_with_invalid_priority(client):
    headers = register_and_login(
        client, "Test User", "invalid_priority_update@example.com"
    )

    task_response = client.post(
        "/tasks",
        json={"title": "Test task", "priority": "medium"},
        headers=headers,
    )
    task_id = task_response.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}",
        json={"priority": "urgent"},
        headers=headers,
    )

    assert response.status_code == 422


def test_update_task_with_title_too_long(client):
    headers = register_and_login(client, "Test User", "long_title_update@example.com")

    task_response = client.post(
        "/tasks",
        json={"title": "Test task", "priority": "medium"},
        headers=headers,
    )
    task_id = task_response.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}",
        json={"title": "A" * 101},
        headers=headers,
    )

    assert response.status_code == 422
