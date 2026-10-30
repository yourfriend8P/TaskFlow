from database import Base, engine
from models import TaskDB

Base.metadata.create_all(bind=engine)

print("MySQL tables created successfully.")
