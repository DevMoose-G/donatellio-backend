import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

import donatellio.orm.models.image
import donatellio.orm.models.project
import donatellio.orm.models.user
from donatellio.orm.base import Base
from donatellio.settings import settings

# Database URL (using async driver)
DATABASE_URL = settings.database_url

# Create the async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,      # set to true for debugging
    future=True
)

# Session factory for dependency injection
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Utility to initialize the database (create tables)
async def init_db():
    print("Tables to create:", Base.metadata.tables.keys())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Dependency to get DB session
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

if __name__=="__main__":
    asyncio.run(init_db())