import sys
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context
# Point to your backend directory to import the database connector
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import getconn

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

def run_migrations_online() -> None:
    connectable = create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()