# bootstrap.py
from sqlalchemy_utils import create_database, database_exists
from sqlalchemy import URL

from alembic import command
from alembic.config import Config
from donna_common.settings import settings
from sqlalchemy import create_engine

# grab the same URL you used in Alembic
url_object = URL.create(
    "postgresql+psycopg2",
    username=settings.database_user,
    password=settings.database_password,  # plain (unescaped) text
    host=settings.database_host,
    port=settings.database_port,
    database=settings.database_name,
)

engine = create_engine(
    url_object,
    connect_args={"sslmode": "require"}
)

# 1) ensure the database exists
if not database_exists(engine.url):
    create_database(engine.url)

# 2) run migrations to bring it up to date
alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head")
