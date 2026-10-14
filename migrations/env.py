"""Alembic environment; the database URL comes only from the environment."""

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from argus.persistence.schema import metadata

config = context.config
url = os.environ.get("ARGUS_DATABASE_URL")
if not url:
    raise RuntimeError("ARGUS_DATABASE_URL is required for migrations")
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = metadata


def run_migrations_offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
