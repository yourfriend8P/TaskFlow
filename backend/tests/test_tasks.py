from models import User, Task, TaskActivity


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
        json={"title": "A" * 151},
        headers=headers,
    )

    assert response.status_code == 422


def test_create_task_with_description_too_long(client):
    headers = register_and_login(client, "Test User", "long_description@example.com")

    response = client.post(
        "/tasks",
        json={
            "title": "Test task",
            "description": "A" * 501,
            "priority": "medium",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_create_task_with_invalid_due_date(client):
    headers = register_and_login(client, "Test User", "invalid_due_date@example.com")

    response = client.post(
        "/tasks",
        json={
            "title": "Test task",
            "priority": "medium",
            "due_date": "not-a-valid-date",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_update_task_with_description_too_long(client):
    headers = register_and_login(
        client, "Test User", "long_update_description@example.com"
    )

    task_response = client.post(
        "/tasks",
        json={"title": "Test task", "priority": "medium"},
        headers=headers,
    )
    task_id = task_response.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}",
        json={"description": "A" * 501},
        headers=headers,
    )

    assert response.status_code == 422


def test_task_pagination_rejects_negative_skip(client):
    headers = register_and_login(client, "Test User", "negative_skip@example.com")

    response = client.get("/tasks?skip=-1", headers=headers)

    assert response.status_code == 422


def test_task_pagination_rejects_negative_limit(client):
    headers = register_and_login(client, "Test User", "negative_limit@example.com")

    response = client.get("/tasks?limit=-1", headers=headers)

    assert response.status_code == 422


def test_filter_tasks_by_invalid_status(client):
    headers = register_and_login(
        client, "Test User", "invalid_status_filter@example.com"
    )

    response = client.get(
        "/tasks?task_status=invalid_status",
        headers=headers,
    )

    assert response.status_code == 400


def test_filter_tasks_by_invalid_priority(client):
    headers = register_and_login(
        client, "Test User", "invalid_priority_filter@example.com"
    )

    response = client.get(
        "/tasks?priority=urgent",
        headers=headers,
    )

    assert response.status_code == 400


def test_filter_overdue_tasks(client):
    headers = register_and_login(client, "Test User", "overdue_filter@example.com")

    overdue_task = client.post(
        "/tasks",
        json={
            "title": "Overdue task",
            "priority": "high",
            "due_date": "2020-01-01T00:00:00Z",
        },
        headers=headers,
    )
    assert overdue_task.status_code == 201

    completed_task = client.post(
        "/tasks",
        json={
            "title": "Completed overdue task",
            "priority": "medium",
            "due_date": "2020-01-01T00:00:00Z",
        },
        headers=headers,
    )
    completed_id = completed_task.json()["id"]

    client.patch(
        f"/tasks/{completed_id}",
        json={"status": "completed"},
        headers=headers,
    )

    response = client.get("/tasks?overdue=true", headers=headers)

    assert response.status_code == 200
    assert [task["title"] for task in response.json()] == ["Overdue task"]


def test_filter_tasks_by_due_before(client):
    headers = register_and_login(client, "Test User", "due_before_filter@example.com")

    client.post(
        "/tasks",
        json={
            "title": "Earlier task",
            "priority": "low",
            "due_date": "2025-01-01T00:00:00Z",
        },
        headers=headers,
    )

    client.post(
        "/tasks",
        json={
            "title": "Later task",
            "priority": "high",
            "due_date": "2030-01-01T00:00:00Z",
        },
        headers=headers,
    )

    response = client.get(
        "/tasks?due_before=2026-01-01T00:00:00Z",
        headers=headers,
    )

    assert response.status_code == 200
    assert [task["title"] for task in response.json()] == ["Earlier task"]


def test_task_search_is_case_insensitive_and_strips_whitespace(client):
    headers = register_and_login(client, "Test User", "search_case@example.com")

    client.post(
        "/tasks",
        json={"title": "Prepare Project Report", "priority": "medium"},
        headers=headers,
    )

    response = client.get(
        "/tasks?search=%20project%20",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Prepare Project Report"


def test_task_pagination_rejects_limit_above_100(client):
    headers = register_and_login(client, "Test User", "large_limit@example.com")

    response = client.get("/tasks?limit=101", headers=headers)

    assert response.status_code == 422


def test_filter_tasks_by_project_id(client):
    headers = register_and_login(client, "Test User", "project_filter@example.com")

    project_a = client.post(
        "/projects",
        json={"name": "Project A", "description": "First project"},
        headers=headers,
    ).json()

    project_b = client.post(
        "/projects",
        json={"name": "Project B", "description": "Second project"},
        headers=headers,
    ).json()

    client.post(
        "/tasks",
        json={
            "title": "Task A",
            "priority": "medium",
            "project_id": project_a["id"],
        },
        headers=headers,
    )

    client.post(
        "/tasks",
        json={
            "title": "Task B",
            "priority": "high",
            "project_id": project_b["id"],
        },
        headers=headers,
    )

    response = client.get(
        f"/tasks?project_id={project_a['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Task A"


def test_filter_tasks_by_project_with_no_tasks(client):
    headers = register_and_login(
        client, "Test User", "empty_project_filter@example.com"
    )

    project = client.post(
        "/projects",
        json={"name": "Empty Project", "description": "No tasks"},
        headers=headers,
    ).json()

    response = client.get(
        f"/tasks?project_id={project['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_project_filter_respects_task_visibility(client):
    owner_headers = register_and_login(client, "Owner", "project_owner@example.com")

    project = client.post(
        "/projects",
        json={"name": "Private Project", "description": "Private"},
        headers=owner_headers,
    ).json()

    client.post(
        "/tasks",
        json={
            "title": "Private task",
            "priority": "medium",
            "project_id": project["id"],
        },
        headers=owner_headers,
    )

    other_headers = register_and_login(
        client, "Other User", "project_other@example.com"
    )

    response = client.get(
        f"/tasks?project_id={project['id']}",
        headers=other_headers,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_task_search_no_match(client):
    headers = register_and_login(client, "Test User", "search_no_match@example.com")

    client.post(
        "/tasks",
        json={"title": "Prepare report", "priority": "medium"},
        headers=headers,
    )

    response = client.get(
        "/tasks?search=nonexistent",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_task_search_whitespace_returns_all_tasks(client):
    headers = register_and_login(client, "Test User", "search_whitespace@example.com")

    for title in ["First task", "Second task"]:
        client.post(
            "/tasks",
            json={"title": title, "priority": "medium"},
            headers=headers,
        )

    response = client.get("/tasks?search=%20%20%20", headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_task_search_respects_user_visibility(client):
    owner_headers = register_and_login(client, "Owner", "search_owner@example.com")

    client.post(
        "/tasks",
        json={"title": "Secret Project Report", "priority": "high"},
        headers=owner_headers,
    )

    other_headers = register_and_login(client, "Other User", "search_other@example.com")

    response = client.get(
        "/tasks?search=Secret",
        headers=other_headers,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_creator_can_get_own_task(client):
    headers = register_and_login(client, "Creator", "get_own_task@example.com")

    created = client.post(
        "/tasks",
        json={"title": "My task", "priority": "medium"},
        headers=headers,
    )
    task_id = created.json()["id"]

    response = client.get(f"/tasks/{task_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["title"] == "My task"


def test_assigned_user_can_get_task(client, db_session):
    upper_headers = register_and_login(
        client, "Supervisor", "get_assigned_upper@example.com"
    )

    upper = (
        db_session.query(User).filter_by(email="get_assigned_upper@example.com").first()
    )
    upper.role = "upper_user"
    db_session.commit()

    user_headers = register_and_login(
        client, "Employee", "get_assigned_user@example.com"
    )

    task = client.post(
        "/tasks",
        json={"title": "Assigned task", "priority": "high"},
        headers=upper_headers,
    )
    task_id = task.json()["id"]

    assignment = client.patch(
        f"/tasks/{task_id}/assign",
        json={
            "assigned_to_id": db_session.query(User)
            .filter_by(email="get_assigned_user@example.com")
            .first()
            .id
        },
        headers=upper_headers,
    )
    assert assignment.status_code == 200

    response = client.get(f"/tasks/{task_id}", headers=user_headers)

    assert response.status_code == 200
    assert response.json()["title"] == "Assigned task"


def test_unrelated_user_cannot_get_task(client):
    owner_headers = register_and_login(client, "Owner", "get_task_owner@example.com")

    task = client.post(
        "/tasks",
        json={"title": "Private task", "priority": "medium"},
        headers=owner_headers,
    )
    task_id = task.json()["id"]

    other_headers = register_and_login(
        client, "Other User", "get_task_other@example.com"
    )

    response = client.get(f"/tasks/{task_id}", headers=other_headers)

    assert response.status_code == 404


def test_user_cannot_get_nonexistent_task(client):
    headers = register_and_login(client, "Test User", "get_missing_task@example.com")

    response = client.get("/tasks/99999", headers=headers)

    assert response.status_code == 404


def test_assign_task_to_nonexistent_user(client, db_session):
    headers = register_and_login(
        client, "Supervisor", "assign_missing_supervisor@example.com"
    )

    supervisor = (
        db_session.query(User)
        .filter_by(email="assign_missing_supervisor@example.com")
        .first()
    )
    supervisor.role = "upper_user"
    db_session.commit()

    task = client.post(
        "/tasks",
        json={"title": "Assignment test", "priority": "medium"},
        headers=headers,
    )
    task_id = task.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": 99999},
        headers=headers,
    )

    assert response.status_code == 404


def test_supervisor_cannot_assign_task_to_another_supervisor(client, db_session):
    headers = register_and_login(
        client, "Supervisor", "assign_upper_target_owner@example.com"
    )

    owner = (
        db_session.query(User)
        .filter_by(email="assign_upper_target_owner@example.com")
        .first()
    )
    owner.role = "upper_user"
    db_session.commit()

    register_and_login(client, "Other Supervisor", "assign_upper_target@example.com")

    target = (
        db_session.query(User)
        .filter_by(email="assign_upper_target@example.com")
        .first()
    )
    target.role = "upper_user"
    db_session.commit()

    task = client.post(
        "/tasks",
        json={"title": "Supervisor assignment test", "priority": "high"},
        headers=headers,
    )
    task_id = task.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": target.id},
        headers=headers,
    )

    assert response.status_code == 400


def test_supervisor_can_reassign_task(client, db_session):
    headers = register_and_login(
        client, "Supervisor", "reassign_supervisor@example.com"
    )

    supervisor = (
        db_session.query(User)
        .filter_by(email="reassign_supervisor@example.com")
        .first()
    )
    supervisor.role = "upper_user"
    db_session.commit()

    register_and_login(client, "User One", "reassign_user_one@example.com")
    register_and_login(client, "User Two", "reassign_user_two@example.com")

    user_one = (
        db_session.query(User).filter_by(email="reassign_user_one@example.com").first()
    )
    user_two = (
        db_session.query(User).filter_by(email="reassign_user_two@example.com").first()
    )

    task = client.post(
        "/tasks",
        json={"title": "Reassignment test", "priority": "medium"},
        headers=headers,
    )
    task_id = task.json()["id"]

    first_assignment = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": user_one.id},
        headers=headers,
    )
    assert first_assignment.status_code == 200

    second_assignment = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": user_two.id},
        headers=headers,
    )

    assert second_assignment.status_code == 200

    db_session.refresh(db_session.query(Task).filter_by(id=task_id).first())
    task_record = db_session.query(Task).filter_by(id=task_id).first()

    assert task_record.assigned_to_id == user_two.id


def test_normal_user_cannot_assign_task(client):
    headers = register_and_login(
        client, "Normal User", "normal_assign_attempt@example.com"
    )

    task = client.post(
        "/tasks",
        json={"title": "Normal user task", "priority": "medium"},
        headers=headers,
    )
    task_id = task.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": 99999},
        headers=headers,
    )

    assert response.status_code == 403


def test_task_assignment_creates_activity(client, db_session):
    headers = register_and_login(
        client, "Supervisor", "activity_assign_supervisor@example.com"
    )

    supervisor = (
        db_session.query(User)
        .filter_by(email="activity_assign_supervisor@example.com")
        .first()
    )
    supervisor.role = "upper_user"
    db_session.commit()

    register_and_login(client, "Employee", "activity_assign_employee@example.com")

    employee = (
        db_session.query(User)
        .filter_by(email="activity_assign_employee@example.com")
        .first()
    )

    task = client.post(
        "/tasks",
        json={"title": "Activity test task", "priority": "medium"},
        headers=headers,
    )
    task_id = task.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": employee.id},
        headers=headers,
    )

    assert response.status_code == 200

    activity = (
        db_session.query(TaskActivity)
        .filter_by(
            task_id=task_id,
            action="task assigned",
        )
        .first()
    )

    assert activity is not None
    assert activity.actor_id == supervisor.id
    assert str(employee.id) in activity.details


def test_task_reassignment_creates_multiple_activities(client, db_session):
    headers = register_and_login(
        client, "Supervisor", "activity_reassign_supervisor@example.com"
    )

    supervisor = (
        db_session.query(User)
        .filter_by(email="activity_reassign_supervisor@example.com")
        .first()
    )
    supervisor.role = "upper_user"
    db_session.commit()

    register_and_login(client, "Employee One", "activity_reassign_one@example.com")
    register_and_login(client, "Employee Two", "activity_reassign_two@example.com")

    user_one = (
        db_session.query(User)
        .filter_by(email="activity_reassign_one@example.com")
        .first()
    )
    user_two = (
        db_session.query(User)
        .filter_by(email="activity_reassign_two@example.com")
        .first()
    )

    task = client.post(
        "/tasks",
        json={"title": "Reassignment history", "priority": "high"},
        headers=headers,
    )
    task_id = task.json()["id"]

    first = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": user_one.id},
        headers=headers,
    )
    second = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": user_two.id},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    activities = (
        db_session.query(TaskActivity)
        .filter_by(
            task_id=task_id,
            action="task assigned",
        )
        .all()
    )

    assert len(activities) == 2
    assert all(activity.actor_id == supervisor.id for activity in activities)
    assert any(str(user_one.id) in activity.details for activity in activities)
    assert any(str(user_two.id) in activity.details for activity in activities)


def test_assigned_user_can_view_task_activities(client, db_session):
    headers = register_and_login(
        client, "Supervisor", "activity_view_supervisor@example.com"
    )

    supervisor = (
        db_session.query(User)
        .filter_by(email="activity_view_supervisor@example.com")
        .first()
    )
    supervisor.role = "upper_user"
    db_session.commit()

    user_headers = register_and_login(
        client, "Employee", "activity_view_employee@example.com"
    )

    employee = (
        db_session.query(User)
        .filter_by(email="activity_view_employee@example.com")
        .first()
    )

    task = client.post(
        "/tasks",
        json={"title": "Activity visibility", "priority": "medium"},
        headers=headers,
    )
    task_id = task.json()["id"]

    assignment = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": employee.id},
        headers=headers,
    )
    assert assignment.status_code == 200

    response = client.get(
        f"/tasks/{task_id}/activities",
        headers=user_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert any(activity["action"] == "task assigned" for activity in response.json())


def test_task_creator_can_view_own_activities(client):
    headers = register_and_login(client, "Creator", "activity_creator@example.com")

    task = client.post(
        "/tasks",
        json={"title": "Creator activity", "priority": "medium"},
        headers=headers,
    )
    task_id = task.json()["id"]

    response = client.get(
        f"/tasks/{task_id}/activities",
        headers=headers,
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)
