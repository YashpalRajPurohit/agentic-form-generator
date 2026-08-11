import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

raw_db_url = os.getenv("DATABASE_URL")

# Inject +psycopg specifically for SQLAlchemy
SQLALCHEMY_DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(SQLALCHEMY_DATABASE_URL)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    pool_pre_ping=True,  # Checks if the connection is alive before using it
    pool_recycle=300     # Safely recycles connections before Neon kills them (every 5 mins)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class for all our database models
Base = declarative_base()

# The dependency we will inject into FastAPI endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()