"""SQLAlchemy declarative base for all ORM models."""

from __future__ import annotations

import json

from sqlalchemy import JSON, Text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class PortableJSONB(TypeDecorator):
    """A JSON column that renders as JSONB on PostgreSQL and JSON/TEXT on SQLite.

    This lets model-level tests run against in-memory SQLite while production
    uses PostgreSQL's native JSONB.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001, ANN201
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is not None and dialect.name == "sqlite":
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is not None and isinstance(value, str):
            return json.loads(value)
        return value


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
