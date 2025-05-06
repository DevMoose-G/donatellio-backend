# bootstrap.py
from sqlalchemy import create_engine
from sqlalchemy_utils import create_database, database_exists
from alembic.config import Config
from alembic import command

from donatellio.settings import settings

# grab the same URL you used in Alembic
DATABASE_URL = settings.database_url

# 1) ensure the database exists
if not database_exists(DATABASE_URL):
    create_database(DATABASE_URL)

# 2) run migrations to bring it up to date
alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head")
