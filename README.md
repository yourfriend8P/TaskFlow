python -m uvicorn main:app --reload

To test specific folder:
$env:PYTHONPATH = "backend"
pytest backend/tests/test_projects.py -v

Note to myself:
Understand security.py and login() endpoint
