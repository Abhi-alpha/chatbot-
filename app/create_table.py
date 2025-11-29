
# create_tables.py
from app.db import Base, engine
from app import models  # This imports the models so SQLAlchemy knows about them

print("Creating tables in the database...")
Base.metadata.create_all(bind=engine)
print("Done!")