from models import User


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


def test_non_admin_cannot_access_dashboard(client):
    headers = register_and_login(client, "Normal User", "normaladmin@example.com")

    response = client.get(
        "/admin/dashboard",
        headers=headers,
    )

    assert response.status_code == 403


def test_admin_can_access_dashboard(client, db_session):
    headers = register_and_login(client, "Admin User", "admin@example.com")

    admin = db_session.query(User).filter_by(email="admin@example.com").first()

    admin.role = "admin"
    db_session.commit()

    # Log in again to get a token after changing the role
    headers = register_and_login(client, "Temporary", "temporary@example.com")

    login = client.post(
        "/auth/login",
        data={
            "username": "admin@example.com",
            "password": "password123",
        },
    )

    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get(
        "/admin/dashboard",
        headers=headers,
    )

    assert response.status_code == 200
    assert "total_users" in response.json()
    assert "total_tasks" in response.json()


def test_non_admin_cannot_list_admin_users(client):
    headers = register_and_login(client, "Regular User", "regularadmin@example.com")

    response = client.get(
        "/admin/users",
        headers=headers,
    )

    assert response.status_code == 403


def create_admin(client, db_session, email):
    register_and_login(client, "Admin", email)

    admin = db_session.query(User).filter_by(email=email).first()

    admin.role = "admin"
    db_session.commit()

    login = client.post(
        "/auth/login",
        data={
            "username": email,
            "password": "password123",
        },
    )

    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_admin_cannot_access_task_list(client, db_session):
    admin_headers = create_admin(client, db_session, "taskadmin@example.com")

    response = client.get("/tasks", headers=admin_headers)

    assert response.status_code == 403


def test_admin_cannot_access_individual_task(client, db_session):
    user_headers = register_and_login(
        client, "Task Owner", "taskowneradmin@example.com"
    )

    task = client.post(
        "/tasks",
        headers=user_headers,
        json={
            "title": "Private Task",
            "description": "",
            "priority": "medium",
        },
    )

    admin_headers = create_admin(client, db_session, "individualadmin@example.com")

    response = client.get(
        f"/tasks/{task.json()['id']}",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_change_own_role(client, db_session):
    admin_headers = create_admin(client, db_session, "selfroleadmin@example.com")

    admin = db_session.query(User).filter_by(email="selfroleadmin@example.com").first()

    response = client.patch(
        f"/admin/users/{admin.id}/role",
        headers=admin_headers,
        json={"role": "user"},
    )

    assert response.status_code == 403


def test_admin_cannot_promote_user_to_admin(client, db_session):
    admin_headers = create_admin(client, db_session, "promotionadmin@example.com")

    user_headers = register_and_login(
        client, "Promotion Target", "promotiontarget@example.com"
    )

    target = (
        db_session.query(User).filter_by(email="promotiontarget@example.com").first()
    )

    response = client.patch(
        f"/admin/users/{target.id}/role",
        headers=admin_headers,
        json={"role": "admin"},
    )

    assert response.status_code == 403


def test_admin_can_deactivate_user(client, db_session):
    admin_headers = create_admin(client, db_session, "deactivateadmin@example.com")

    register_and_login(client, "Target User", "targetdeactivate@example.com")

    target = (
        db_session.query(User).filter_by(email="targetdeactivate@example.com").first()
    )

    response = client.patch(
        f"/admin/users/{target.id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_deactivated_user_cannot_login(client, db_session):
    register_and_login(client, "Inactive User", "inactive@example.com")

    user = db_session.query(User).filter_by(email="inactive@example.com").first()

    user.is_active = False
    db_session.commit()

    response = client.post(
        "/auth/login",
        data={
            "username": "inactive@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 403


def test_admin_cannot_deactivate_self(client, db_session):
    admin_headers = create_admin(client, db_session, "selfdeactivate@example.com")

    admin = db_session.query(User).filter_by(email="selfdeactivate@example.com").first()

    response = client.patch(
        f"/admin/users/{admin.id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )

    assert response.status_code == 403


def test_admin_cannot_create_task(client, db_session):
    admin_headers = create_admin(client, db_session, "admintask@example.com")

    response = client.post(
        "/tasks",
        headers=admin_headers,
        json={
            "title": "Admin Task",
            "description": "This should not be allowed",
            "priority": "medium",
        },
    )

    assert response.status_code == 403


def test_admin_cannot_create_project(client, db_session):
    admin_headers = create_admin(client, db_session, "adminproject@example.com")

    response = client.post(
        "/projects",
        headers=admin_headers,
        json={
            "name": "Admin Project",
            "description": "This should not be allowed",
        },
    )

    assert response.status_code == 403


def test_admin_cannot_access_individual_project(client, db_session):
    user_headers = register_and_login(
        client, "Project Owner", "projectowner@example.com"
    )

    project_response = client.post(
        "/projects",
        headers=user_headers,
        json={
            "name": "Private Project",
            "description": "Only the owner should access this",
        },
    )

    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    admin_headers = create_admin(client, db_session, "projectadmin@example.com")

    response = client.get(
        f"/projects/{project_id}",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_access_project_tasks(client, db_session):
    user_headers = register_and_login(
        client, "Project Owner", "projecttasksowner@example.com"
    )

    project_response = client.post(
        "/projects",
        headers=user_headers,
        json={
            "name": "Private Tasks Project",
            "description": "Private project tasks",
        },
    )

    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    admin_headers = create_admin(client, db_session, "projecttasksadmin@example.com")

    response = client.get(
        f"/projects/{project_id}/tasks",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_access_task_activity(client, db_session):
    user_headers = register_and_login(
        client, "Activity Owner", "activityowner@example.com"
    )

    task_response = client.post(
        "/tasks",
        headers=user_headers,
        json={
            "title": "Private Activity Task",
            "description": "Testing activity privacy",
            "priority": "medium",
        },
    )

    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    admin_headers = create_admin(client, db_session, "activityadmin@example.com")

    response = client.get(
        f"/tasks/{task_id}/activities",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_deactivate_another_admin(client, db_session):
    register_and_login(client, "First Admin", "firstadmin@example.com")

    first_admin = (
        db_session.query(User).filter_by(email="firstadmin@example.com").first()
    )

    first_admin.role = "admin"
    db_session.commit()

    second_admin_headers = create_admin(client, db_session, "secondadmin@example.com")

    response = client.patch(
        f"/admin/users/{first_admin.id}/status",
        headers=second_admin_headers,
        json={"is_active": False},
    )

    assert response.status_code == 403


def test_upper_user_cannot_deactivate_user(client, db_session):
    # Create upper user
    register_and_login(client, "Supervisor", "supervisor@example.com")

    supervisor = (
        db_session.query(User).filter_by(email="supervisor@example.com").first()
    )

    supervisor.role = "upper_user"
    db_session.commit()

    upper_headers = register_and_login(
        client, "Another User", "anotheruser@example.com"
    )

    target = db_session.query(User).filter_by(email="anotheruser@example.com").first()

    response = client.patch(
        f"/admin/users/{target.id}/status",
        headers=upper_headers,
        json={"is_active": False},
    )

    assert response.status_code == 403


def test_upper_user_cannot_change_user_role(client, db_session):
    upper_headers = register_and_login(client, "Supervisor", "upper_role@example.com")

    supervisor = (
        db_session.query(User).filter_by(email="upper_role@example.com").first()
    )
    supervisor.role = "upper_user"
    db_session.commit()

    register_and_login(client, "Target User", "upper_role_target@example.com")

    target = (
        db_session.query(User).filter_by(email="upper_role_target@example.com").first()
    )

    response = client.patch(
        f"/admin/users/{target.id}/role",
        json={"role": "upper_user"},
        headers=upper_headers,
    )

    assert response.status_code == 403
    assert target.role == "user"


def test_normal_user_cannot_change_user_role(client, db_session):
    user_headers = register_and_login(client, "Normal User", "normalrole@example.com")

    register_and_login(client, "Target User", "targetrole@example.com")

    target = db_session.query(User).filter_by(email="targetrole@example.com").first()

    response = client.patch(
        f"/admin/users/{target.id}/role",
        headers=user_headers,
        json={"role": "upper_user"},
    )

    assert response.status_code == 403


def test_deactivated_user_cannot_use_existing_token(client, db_session):
    # Register and log in as a normal user
    user_headers = register_and_login(client, "Token User", "tokenuser@example.com")

    user = db_session.query(User).filter_by(email="tokenuser@example.com").first()

    # Create admin
    admin_headers = create_admin(client, db_session, "tokenadmin@example.com")

    # Admin deactivates the user
    deactivate_response = client.patch(
        f"/admin/users/{user.id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )

    assert deactivate_response.status_code == 200

    # Try using the previously issued token
    response = client.get(
        "/tasks",
        headers=user_headers,
    )

    assert response.status_code == 401


def test_upper_user_cannot_access_admin_dashboard(client, db_session):
    upper_headers = register_and_login(
        client, "Supervisor", "dashboard_supervisor@example.com"
    )

    supervisor = (
        db_session.query(User)
        .filter_by(email="dashboard_supervisor@example.com")
        .first()
    )

    supervisor.role = "upper_user"
    db_session.commit()

    response = client.get(
        "/admin/dashboard",
        headers=upper_headers,
    )

    assert response.status_code == 403


def test_normal_user_cannot_access_admin_dashboard(client):
    user_headers = register_and_login(
        client, "Normal User", "normal_dashboard@example.com"
    )

    response = client.get(
        "/admin/dashboard",
        headers=user_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_assign_tasks(client, db_session):
    admin_headers = create_admin(client, db_session, "admin_assign@example.com")

    user_headers = register_and_login(client, "Task Owner", "task_owner@example.com")

    task_response = client.post(
        "/tasks",
        json={"title": "Test task", "priority": "medium"},
        headers=user_headers,
    )

    assert task_response.status_code == 201

    task_id = task_response.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": 1},
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_update_individual_task(client, db_session):
    user_headers = register_and_login(client, "Task Owner", "update_owner@example.com")

    admin_headers = create_admin(client, db_session, "admin_update@example.com")

    task_response = client.post(
        "/tasks",
        json={"title": "Original task", "priority": "medium"},
        headers=user_headers,
    )

    assert task_response.status_code == 201

    task_id = task_response.json()["id"]

    response = client.patch(
        f"/tasks/{task_id}",
        json={"title": "Updated by admin"},
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_delete_individual_task(client, db_session):
    user_headers = register_and_login(client, "Task Owner", "delete_owner@example.com")

    admin_headers = create_admin(client, db_session, "admin_delete@example.com")

    task_response = client.post(
        "/tasks",
        json={"title": "Task to delete", "priority": "medium"},
        headers=user_headers,
    )

    assert task_response.status_code == 201

    task_id = task_response.json()["id"]

    response = client.delete(
        f"/tasks/{task_id}",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_update_individual_project(client, db_session):
    user_headers = register_and_login(
        client, "Project Owner", "project_update_owner@example.com"
    )

    admin_headers = create_admin(client, db_session, "admin_project_update@example.com")

    project_response = client.post(
        "/projects",
        json={"name": "Original Project", "description": "Test project"},
        headers=user_headers,
    )

    assert project_response.status_code == 201

    project_id = project_response.json()["id"]

    response = client.patch(
        f"/projects/{project_id}",
        json={"name": "Updated by admin"},
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_delete_individual_project(client, db_session):
    user_headers = register_and_login(
        client, "Project Owner", "project_delete_owner@example.com"
    )

    admin_headers = create_admin(client, db_session, "admin_project_delete@example.com")

    project_response = client.post(
        "/projects",
        json={"name": "Project to delete", "description": "Test project"},
        headers=user_headers,
    )

    assert project_response.status_code == 201

    project_id = project_response.json()["id"]

    response = client.delete(
        f"/projects/{project_id}",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_access_project_tasks(client, db_session):
    user_headers = register_and_login(
        client, "Project Owner", "project_tasks_owner@example.com"
    )

    admin_headers = create_admin(client, db_session, "admin_project_tasks@example.com")

    project_response = client.post(
        "/projects",
        json={"name": "Private Project", "description": "Test project"},
        headers=user_headers,
    )

    assert project_response.status_code == 201

    project_id = project_response.json()["id"]

    response = client.get(
        f"/projects/{project_id}/tasks",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_access_task_activities(client, db_session):
    user_headers = register_and_login(
        client, "Task Owner", "activity_owner@example.com"
    )

    admin_headers = create_admin(client, db_session, "admin_activity@example.com")

    task_response = client.post(
        "/tasks",
        json={"title": "Activity test task", "priority": "medium"},
        headers=user_headers,
    )

    assert task_response.status_code == 201

    task_id = task_response.json()["id"]

    response = client.get(
        f"/tasks/{task_id}/activities",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_normal_user_cannot_assign_tasks(client, db_session):
    user_headers = register_and_login(
        client, "Task Owner", "normal_assign_owner@example.com"
    )

    another_user_headers = register_and_login(
        client, "Another User", "normal_assign_target@example.com"
    )

    task_response = client.post(
        "/tasks",
        json={"title": "Assignment test", "priority": "medium"},
        headers=user_headers,
    )

    assert task_response.status_code == 201

    task_id = task_response.json()["id"]

    target = (
        db_session.query(User)
        .filter_by(email="normal_assign_target@example.com")
        .first()
    )

    response = client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to_id": target.id},
        headers=user_headers,
    )

    assert response.status_code == 403


def test_normal_user_cannot_deactivate_another_user(client, db_session):
    user_headers = register_and_login(
        client, "Normal User", "normal_deactivate@example.com"
    )

    target_headers = register_and_login(
        client, "Target User", "target_deactivate@example.com"
    )

    target = (
        db_session.query(User).filter_by(email="target_deactivate@example.com").first()
    )

    response = client.patch(
        f"/admin/users/{target.id}/status",
        json={"is_active": False},
        headers=user_headers,
    )

    assert response.status_code == 403
    assert target.is_active is True


def test_normal_user_cannot_access_admin_user_list(client):
    user_headers = register_and_login(
        client, "Normal User", "normal_user_list@example.com"
    )

    response = client.get(
        "/admin/users",
        headers=user_headers,
    )

    assert response.status_code == 403


def test_upper_user_cannot_access_admin_user_list(client, db_session):
    upper_headers = register_and_login(
        client, "Supervisor", "supervisor_user_list@example.com"
    )

    supervisor = (
        db_session.query(User)
        .filter_by(email="supervisor_user_list@example.com")
        .first()
    )

    supervisor.role = "upper_user"
    db_session.commit()

    response = client.get(
        "/admin/users",
        headers=upper_headers,
    )

    assert response.status_code == 403


def test_admin_can_list_users(client, db_session):
    admin_headers = create_admin(client, db_session, "admin_list_success@example.com")

    response = client.get(
        "/admin/users",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_upper_user_cannot_deactivate_user(client, db_session):
    upper_headers = register_and_login(
        client, "Supervisor", "upper_deactivate@example.com"
    )

    supervisor = (
        db_session.query(User).filter_by(email="upper_deactivate@example.com").first()
    )
    supervisor.role = "upper_user"
    db_session.commit()

    register_and_login(client, "Target User", "upper_deactivate_target@example.com")

    target = (
        db_session.query(User)
        .filter_by(email="upper_deactivate_target@example.com")
        .first()
    )

    response = client.patch(
        f"/admin/users/{target.id}/status",
        json={"is_active": False},
        headers=upper_headers,
    )

    assert response.status_code == 403
    assert target.is_active is True


def test_admin_can_promote_user_to_upper_user(client, db_session):
    admin_headers = create_admin(client, db_session, "admin_promote_upper@example.com")

    register_and_login(client, "Target User", "promote_upper_target@example.com")

    target = (
        db_session.query(User)
        .filter_by(email="promote_upper_target@example.com")
        .first()
    )

    response = client.patch(
        f"/admin/users/{target.id}/role",
        json={"role": "upper_user"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert target.role == "upper_user"


def test_admin_can_deactivate_user_already_inactive(client, db_session):
    admin_headers = create_admin(client, db_session, "admin_inactive@example.com")

    register_and_login(client, "Inactive User", "already_inactive@example.com")

    target = (
        db_session.query(User).filter_by(email="already_inactive@example.com").first()
    )

    target.is_active = False
    db_session.commit()

    response = client.patch(
        f"/admin/users/{target.id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert target.is_active is False
