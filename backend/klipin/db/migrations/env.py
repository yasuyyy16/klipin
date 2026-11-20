from alembic import context

from klipin.db.models import Base, include_in_autogenerate

target_metadata = Base.metadata


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=True, include_object=include_in_autogenerate)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:
    from klipin.db.session import get_engine

    with get_engine().begin() as conn:
        _run(conn)
