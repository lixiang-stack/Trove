from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from trove.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    assert url is not None
    # SQLite's DBAPI leaves DDL in autocommit mode unless BEGIN is explicit.
    # Own the transaction here so a failed migration cannot leave half-applied
    # schema changes behind a rolled-back alembic_version row.
    connectable = create_engine(url, poolclass=pool.NullPool, isolation_level="AUTOCOMMIT")
    with connectable.connect() as connection:
        connection.exec_driver_sql("BEGIN")
        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                transactional_ddl=False,
            )
            context.run_migrations()
            connection.exec_driver_sql("COMMIT")
        except BaseException:
            connection.exec_driver_sql("ROLLBACK")
            raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
