from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from klipin.db.session import get_engine, get_sessionmaker


def get_db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


def get_db_engine() -> Engine:
    """Untuk endpoint berumur panjang (SSE) yang membuka koneksi sendiri per polling."""
    return get_engine()


DbSession = Annotated[Session, Depends(get_db)]
DbEngine = Annotated[Engine, Depends(get_db_engine)]
