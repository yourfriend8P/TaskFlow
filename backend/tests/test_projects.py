from models import User, Project, Task


def create_admin(client, db_session, email):
    headers = register_and_login(client, "Test Admin", email)

    admin = db_session.query(User).filter_by(email=email).first()
    admin.role = "admin"
    db_session.commit()

    return headers


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


def test_create_project(client):
    headers = register_and_login(client, "Project Owner", "projectowner@example.com")

    response = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "Website Development",
            "description": "Develop a company website",
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Website Development"


def test_list_own_projects(client):
    headers = register_and_login(client, "Project Lister", "projectlister@example.com")

    client.post(
        "/projects",
        headers=headers,
        json={
            "name": "My Project",
            "description": "My project description",
        },
    )

    response = client.get("/projects", headers=headers)

    assert response.status_code == 200
    assert any(project["name"] == "My Project" for project in response.json())


def test_user_cannot_see_other_users_projects(client):
    owner_headers = register_and_login(
        client, "Project Owner Two", "projectowner2@example.com"
    )

    other_headers = register_and_login(
        client, "Other User", "otherprojectuser@example.com"
    )

    client.post(
        "/projects",
        headers=owner_headers,
        json={
            "name": "Private Project",
            "description": "",
        },
    )

    response = client.get("/projects", headers=other_headers)

    assert response.status_code == 200
    assert all(project["name"] != "Private Project" for project in response.json())


def test_update_project(client):
    headers = register_and_login(client, "Project Editor", "projecteditor@example.com")

    project = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "Original Project",
            "description": "Original description",
        },
    )

    project_id = project.json()["id"]

    response = client.patch(
        f"/projects/{project_id}",
        headers=headers,
        json={
            "name": "Updated Project",
            "description": "Updated description",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Project"
    assert response.json()["description"] == "Updated description"


def test_update_project_with_empty_body(client):
    headers = register_and_login(client, "Empty Project", "emptyproject@example.com")

    project = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "Project Empty",
            "description": "",
        },
    )

    response = client.patch(
        f"/projects/{project.json()['id']}",
        headers=headers,
        json={},
    )

    assert response.status_code == 400


def test_delete_project(client):
    headers = register_and_login(
        client, "Project Deleter", "projectdeleter@example.com"
    )

    project = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "Project To Delete",
            "description": "",
        },
    )

    project_id = project.json()["id"]

    response = client.delete(
        f"/projects/{project_id}",
        headers=headers,
    )

    assert response.status_code == 200

    get_response = client.get(
        f"/projects/{project_id}",
        headers=headers,
    )

    assert get_response.status_code == 404


def test_create_task_inside_project(client):
    headers = register_and_login(client, "Integration User", "integration@example.com")

    project = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "Integration Project",
            "description": "",
        },
    )

    project_id = project.json()["id"]

    task = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Project Task",
            "description": "Task inside project",
            "priority": "high",
            "project_id": project_id,
        },
    )

    assert task.status_code == 201
    assert task.json()["project_id"] == project_id


def test_delete_project_detaches_tasks(client):
    headers = register_and_login(client, "Detach User", "detach@example.com")

    project = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "Project With Task",
            "description": "",
        },
    )

    project_id = project.json()["id"]

    task = client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Task That Must Remain",
            "description": "",
            "priority": "medium",
            "project_id": project_id,
        },
    )

    task_id = task.json()["id"]

    delete_response = client.delete(
        f"/projects/{project_id}",
        headers=headers,
    )

    assert delete_response.status_code == 200

    task_response = client.get(
        f"/tasks/{task_id}",
        headers=headers,
    )

    assert task_response.status_code == 200
    assert task_response.json()["title"] == "Task That Must Remain"
    assert task_response.json()["project_id"] is None


def test_user_can_access_own_project(client):
    user_headers = register_and_login(
        client, "Project Owner", "own_project_access@example.com"
    )

    project_response = client.post(
        "/projects",
        json={
            "name": "My Project",
            "description": "Private project",
        },
        headers=user_headers,
    )

    assert project_response.status_code == 201

    project_id = project_response.json()["id"]

    response = client.get(
        f"/projects/{project_id}",
        headers=user_headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == project_id


def test_user_can_get_own_project(client, db_session):
    headers = register_and_login(client, "Owner", "projectowner1@example.com")

    owner = db_session.query(User).filter_by(email="projectowner1@example.com").first()

    project = Project(
        name="My Project",
        description="My project description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.get(
        f"/projects/{project.id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "My Project"


def test_user_cannot_get_another_users_project(client, db_session):
    owner_headers = register_and_login(client, "Owner", "projectowner2@example.com")
    other_headers = register_and_login(client, "Other", "projectother2@example.com")

    owner = db_session.query(User).filter_by(email="projectowner2@example.com").first()

    project = Project(
        name="Private Project",
        description="Private description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.get(
        f"/projects/{project.id}",
        headers=other_headers,
    )

    assert response.status_code == 404


def test_user_can_update_own_project(client, db_session):
    headers = register_and_login(client, "Owner", "projectowner3@example.com")

    owner = db_session.query(User).filter_by(email="projectowner3@example.com").first()

    project = Project(
        name="Old Name",
        description="Old description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.patch(
        f"/projects/{project.id}",
        json={"name": "Updated Name"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


def test_user_cannot_update_another_users_project(client, db_session):
    register_and_login(client, "Owner", "projectowner4@example.com")
    other_headers = register_and_login(client, "Other", "projectother4@example.com")

    owner = db_session.query(User).filter_by(email="projectowner4@example.com").first()

    project = Project(
        name="Private Project",
        description="Private description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.patch(
        f"/projects/{project.id}",
        json={"name": "Unauthorized Update"},
        headers=other_headers,
    )

    assert response.status_code == 404


def test_admin_cannot_get_individual_project(client, db_session):
    admin_headers = create_admin(client, db_session, "projectadmin1@example.com")

    response = client.get(
        "/projects/1",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_update_individual_project(client, db_session):
    admin_headers = create_admin(client, db_session, "projectadmin2@example.com")

    response = client.patch(
        "/projects/1",
        json={"name": "Updated Project"},
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_project_update_rejects_empty_body(client, db_session):
    headers = register_and_login(client, "Owner", "projectempty@example.com")

    owner = db_session.query(User).filter_by(email="projectempty@example.com").first()

    project = Project(
        name="Original Project",
        description="Original description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.patch(
        f"/projects/{project.id}",
        json={},
        headers=headers,
    )

    assert response.status_code == 400


def test_project_update_rejects_null_name(client, db_session):
    headers = register_and_login(client, "Owner", "projectnull@example.com")

    owner = db_session.query(User).filter_by(email="projectnull@example.com").first()

    project = Project(
        name="Original Project",
        description="Original description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.patch(
        f"/projects/{project.id}",
        json={"name": None},
        headers=headers,
    )

    assert response.status_code == 422


def test_user_can_delete_own_project_and_detach_tasks(client, db_session):
    headers = register_and_login(client, "Owner", "projectdelete1@example.com")

    owner = db_session.query(User).filter_by(email="projectdelete1@example.com").first()

    project = Project(
        name="Project to Delete",
        description="Project description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    task = Task(
        title="Keep This Task",
        description="This task should remain",
        priority="medium",
        project_id=project.id,
        created_by_id=owner.id,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    project_id = project.id
    task_id = task.id

    response = client.delete(
        f"/projects/{project_id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Project deleted successfully"

    assert db_session.get(Project, project_id) is None

    remaining_task = db_session.get(Task, task_id)
    assert remaining_task is not None
    assert remaining_task.project_id is None


def test_user_cannot_delete_another_users_project(client, db_session):
    register_and_login(client, "Owner", "projectdelete2@example.com")
    other_headers = register_and_login(
        client, "Other", "projectotherdelete2@example.com"
    )

    owner = db_session.query(User).filter_by(email="projectdelete2@example.com").first()

    project = Project(
        name="Private Project",
        description="Private description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.delete(
        f"/projects/{project.id}",
        headers=other_headers,
    )

    assert response.status_code == 404
    assert db_session.get(Project, project.id) is not None


def test_admin_cannot_delete_individual_project(client, db_session):
    admin_headers = create_admin(client, db_session, "projectdeleteadmin@example.com")

    response = client.delete(
        "/projects/1",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_delete_nonexistent_project_returns_404(client):
    headers = register_and_login(client, "Owner", "projectdelete404@example.com")

    response = client.delete(
        "/projects/999999",
        headers=headers,
    )

    assert response.status_code == 404


def test_user_can_view_own_project_tasks(client, db_session):
    headers = register_and_login(client, "Owner", "viewtasks1@example.com")

    owner = db_session.query(User).filter_by(email="viewtasks1@example.com").first()

    project = Project(
        name="My Project",
        description="Project description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    task = Task(
        title="My Project Task",
        description="Task description",
        priority="medium",
        created_by_id=owner.id,
        project_id=project.id,
    )
    db_session.add(task)
    db_session.commit()

    response = client.get(
        f"/projects/{project.id}/tasks",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "My Project Task"


def test_user_cannot_view_another_users_project_tasks(client, db_session):
    register_and_login(client, "Owner", "viewtasks2@example.com")
    other_headers = register_and_login(client, "Other", "viewtasksother2@example.com")

    owner = db_session.query(User).filter_by(email="viewtasks2@example.com").first()

    project = Project(
        name="Private Project",
        description="Private description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    task = Task(
        title="Private Task",
        description="Private task description",
        priority="medium",
        created_by_id=owner.id,
        project_id=project.id,
    )
    db_session.add(task)
    db_session.commit()

    response = client.get(
        f"/projects/{project.id}/tasks",
        headers=other_headers,
    )

    assert response.status_code == 404


def test_admin_cannot_view_project_tasks(client, db_session):
    admin_headers = create_admin(client, db_session, "viewtasksadmin@example.com")

    response = client.get(
        "/projects/1/tasks",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_project_with_no_tasks_returns_empty_list(client, db_session):
    headers = register_and_login(client, "Owner", "viewtasks4@example.com")

    owner = db_session.query(User).filter_by(email="viewtasks4@example.com").first()

    project = Project(
        name="Empty Project",
        description="No tasks yet",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.get(
        f"/projects/{project.id}/tasks",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_task_remains_accessible_after_project_deletion(client, db_session):
    headers = register_and_login(client, "Owner", "crossfeature1@example.com")

    owner = db_session.query(User).filter_by(email="crossfeature1@example.com").first()

    project = Project(
        name="Project to Delete",
        description="Project description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    task = Task(
        title="Independent Task",
        description="This task should remain",
        priority="medium",
        created_by_id=owner.id,
        project_id=project.id,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    task_id = task.id

    delete_response = client.delete(
        f"/projects/{project.id}",
        headers=headers,
    )

    assert delete_response.status_code == 200

    task_response = client.get(
        f"/tasks/{task_id}",
        headers=headers,
    )

    assert task_response.status_code == 200
    assert task_response.json()["title"] == "Independent Task"


def test_detached_task_can_still_be_updated(client, db_session):
    headers = register_and_login(client, "Owner", "crossfeature2@example.com")

    owner = db_session.query(User).filter_by(email="crossfeature2@example.com").first()

    project = Project(
        name="Project to Delete",
        description="Project description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    task = Task(
        title="Original Task",
        description="Original description",
        priority="medium",
        created_by_id=owner.id,
        project_id=project.id,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    task_id = task.id

    delete_response = client.delete(
        f"/projects/{project.id}",
        headers=headers,
    )
    assert delete_response.status_code == 200

    update_response = client.patch(
        f"/tasks/{task_id}",
        json={"title": "Updated Task"},
        headers=headers,
    )

    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated Task"
    assert update_response.json()["project_id"] is None


def test_project_task_list_reflects_newly_created_tasks(client, db_session):
    headers = register_and_login(client, "Owner", "crossfeature3@example.com")

    owner = db_session.query(User).filter_by(email="crossfeature3@example.com").first()

    project = Project(
        name="Existing Project",
        description="Project description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    create_response = client.post(
        "/tasks",
        json={
            "title": "New Project Task",
            "description": "Created after the project",
            "priority": "high",
            "project_id": project.id,
        },
        headers=headers,
    )

    assert create_response.status_code == 201

    response = client.get(
        f"/projects/{project.id}/tasks",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "New Project Task"


def test_project_update_does_not_modify_associated_tasks(client, db_session):
    headers = register_and_login(client, "Owner", "crossfeature4@example.com")

    owner = db_session.query(User).filter_by(email="crossfeature4@example.com").first()

    project = Project(
        name="Original Project",
        description="Original description",
        created_by_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    task = Task(
        title="Original Task",
        description="Original task description",
        priority="high",
        created_by_id=owner.id,
        project_id=project.id,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    task_id = task.id

    response = client.patch(
        f"/projects/{project.id}",
        json={
            "name": "Updated Project",
            "description": "Updated description",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Project"

    unchanged_task = db_session.get(Task, task_id)

    assert unchanged_task is not None
    assert unchanged_task.title == "Original Task"
    assert unchanged_task.description == "Original task description"
    assert unchanged_task.priority == "high"
    assert unchanged_task.project_id == project.id
