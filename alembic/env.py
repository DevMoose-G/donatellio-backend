from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy import URL

from alembic import context
from alembic.config import Config
from donna_common.settings import settings
from configparser import RawConfigParser

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
# config = context.config

# this is your SQLAlchemy URL object
# DATABASE_URL = settings.database_url
url_object = URL.create(
    "postgresql+psycopg2",
    username=settings.database_user,
    password=settings.database_password,  # plain (unescaped) text
    host=settings.database_host,
    port=settings.database_port,
    database=settings.database_name,
)

# standard Alembic boilerplate
config = context.config
fileConfig(config.config_file_name)

# override the section dictionary directly
section = config.get_section(config.config_ini_section)
section["sqlalchemy.url"] = url_object.render_as_string(hide_password=False)

# now build the engine from that in-memory dict


# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
from donna_common.orm.base import Base

# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(obj, name, type_, reflected, compare_to):
    # skip attempts to create or alter the asset_stage_enum type
    if type_ == "type" and name == "asset_stage_enum":
        return False
    return True

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
