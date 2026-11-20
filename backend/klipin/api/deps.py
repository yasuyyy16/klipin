from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from klipin.db.session import get_sessionmaker


def get_db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
