from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PartnerWalletTransfer(Base):
    __tablename__ = "partner_wallet_transfers"
    __table_args__ = (
        Index("ix_partner_wallet_transfers_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rox_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    wallet_transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallet_transactions.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
