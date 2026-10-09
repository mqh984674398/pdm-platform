from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for application tables (Alembic target metadata)."""
