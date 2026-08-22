import json
import os
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Integer, MetaData, Table, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql import func

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/coheart",
)

metadata = MetaData()
app_state = Table(
    "app_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("state", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

_engine: Optional[Engine] = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return _engine


def initialize_database() -> None:
    metadata.create_all(get_engine())


def load_state() -> Optional[dict[str, Any]]:
    with get_engine().connect() as connection:
        row = connection.execute(select(app_state.c.state).where(app_state.c.id == 1)).first()
    return row[0] if row else None


def save_state(state: dict[str, Any]) -> None:
    engine = get_engine()
    with engine.begin() as connection:
        statement = insert(app_state).values(id=1, state=state)
        statement = statement.on_conflict_do_update(
            index_elements=[app_state.c.id],
            set_={"state": statement.excluded.state, "updated_at": func.now()},
        )
        connection.execute(statement)


def load_legacy_state(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
