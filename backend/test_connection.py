from sqlalchemy import text

from database import engine

with engine.connect() as connection:
    result = connection.execute(text("SELECT current_database(), current_user"))
    database, user = result.fetchone()

    print("Connected database:", database)
    print("Connected user:", user)
