import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

raw_db_url = os.getenv("DATABASE_URL")

# Inject +psycopg specifically for SQLAlchemy
SQLALCHEMY_DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)

# 1. Define these as None initially so they don't boot up on import
engine = None
SessionLocal = None

# Base MUST remain at the module level so your models can import it
Base = declarative_base()

# 2. Lazy-load initialization function
def init_db():
    global engine, SessionLocal
    if engine is None:
        engine = create_engine(
            SQLALCHEMY_DATABASE_URL, 
            pool_pre_ping=True,  # Checks if the connection is alive before using it
            pool_recycle=300     # Safely recycles connections before Neon kills them (every 5 mins)
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. Clean shutdown function
def close_db():
    global engine
    if engine is not None:
        engine.dispose()

# 4. The dependency injected into FastAPI endpoints
def get_db():
    # Guarantee the engine exists before yielding a session
    if SessionLocal is None:
        init_db()
        
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()