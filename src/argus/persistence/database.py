"""Explicit database engine construction."""

from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.engine import Engine


def create_engine(database_url: str) -> Engine:
    if not database_url:
        raise ValueError("database_url is required")
    return sqlalchemy_create_engine(database_url, pool_pre_ping=True)
