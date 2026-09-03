from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @declared_attr
    def __mapper_args__(cls) -> dict[str, object]:
        # Fetch server-generated timestamps via RETURNING on INSERT/UPDATE.
        # Without this, ``updated_at`` expires after every UPDATE (server-side
        # ``onupdate``) and a later sync access in an async session raises
        # ``sqlalchemy.exc.MissingGreenlet`` (HTTP 500 on POST /payments).
        return {"eager_defaults": True}
