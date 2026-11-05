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
