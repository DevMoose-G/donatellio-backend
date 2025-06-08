# bootstrap.py
from sqlalchemy_utils import create_database, database_exists

from alembic import command
from alembic.config import Config
from donna_common.settings import settings

# grab the same URL you used in Alembic
DATABASE_URL = settings.database_sync_url

# 1) ensure the database exists
if not database_exists(DATABASE_URL):
    create_database(DATABASE_URL)

# 2) run migrations to bring it up to date
alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head")
