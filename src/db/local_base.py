"""SQLAlchemy declarative base for the local accountability database.

This is entirely separate from the Postgres declarative base in base.py.
The local DB uses SQLite via aiosqlite and has its own engine, session
factory, and model registry.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class LocalBase(DeclarativeBase):
    """Base class for all local SQLite accountability models."""
