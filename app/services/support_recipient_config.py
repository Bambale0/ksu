from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminRuntimeSetting
from app.db.models import AdminAccount, User
from app.services.admin_policy import AdminPolicy
from app.services.admin_security import parse_bootstrap_ids

logger = logging.getLogger(__name__)

SUPPORT_RECIPIENT_SETTING_KEY = "support_incoming_recipients"


class SupportRecipientConfigService:
    """Persist explicit operator membership independently of bootstrap credentials."""

    @staticmethod
    def eligible(user: User, account: AdminAccount) -> bool:
        return bool(
            user.is_active and account.is_active
            and AdminPolicy.has_permission(account, "support.read")
        )

    @staticmethod
    async def policy(
        session: AsyncSession, *, lock: bool = False, for_update: bool = False,
    ) -> AdminRuntimeSetting | None:
        statement = select(AdminRuntimeSetting).where(
            AdminRuntimeSetting.key == SUPPORT_RECIPIENT_SETTING_KEY,
        ).execution_options(populate_existing=True)
        if for_update:
            statement = statement.with_for_update()
        elif lock:
            statement = statement.with_for_update(read=True)
        return await session.scalar(statement)

    @staticmethod
    def revision(row: AdminRuntimeSetting | None) -> int:
        value = row.value if row is not None and isinstance(row.value, dict) else {}
        revision = value.get("revision")
        return revision if type(revision) is int and revision >= 0 else 0

    @staticmethod
    def admin_ids(row: AdminRuntimeSetting | None) -> set[uuid.UUID]:
        if row is None:
            return set()
        value = row.value if isinstance(row.value, dict) else {}
        raw = value.get("admin_ids")
        revision = value.get("revision")
        try:
            if (
                type(revision) is not int or revision < 0
                or not isinstance(raw, list) or any(not isinstance(item, str) for item in raw)
            ):
                raise ValueError("Invalid support recipient policy")
            return {uuid.UUID(item) for item in raw}
        except (ValueError, TypeError, AttributeError):
            logger.warning("support_recipient_policy_invalid")
            return set()

    @classmethod
    async def seed_from_bootstrap(cls, session: AsyncSession) -> None:
        """Import once; an existing empty policy is an explicit opt-out."""
        if await cls.policy(session) is not None:
            return
        configured_ids = parse_bootstrap_ids()
        if not configured_ids:
            return
        rows = (await session.execute(
            select(User, AdminAccount)
            .join(AdminAccount, AdminAccount.user_id == User.id)
            .where(
                User.telegram_id.in_(configured_ids),
                User.is_active.is_(True),
                AdminAccount.is_active.is_(True),
            )
            .order_by(AdminAccount.id)
        )).all()
        accounts = [account for user, account in rows if cls.eligible(user, account)]
        # Fresh install: enrollment must still be able to initialize the first owner.
        if not accounts:
            return
        result = await session.execute(
            pg_insert(AdminRuntimeSetting).values(
                key=SUPPORT_RECIPIENT_SETTING_KEY,
                value={
                    "revision": 1,
                    "admin_ids": [str(account.id) for account in accounts],
                    "source": "bootstrap",
                },
                updated_by_admin_id=accounts[0].id,
            ).on_conflict_do_nothing(index_elements=[AdminRuntimeSetting.key]),
        )
        if result.rowcount:
            logger.info(
                "support_recipients_bootstrap_imported",
                extra={"recipient_count": len(accounts)},
            )

    @classmethod
    async def prepare_change(
        cls, session: AsyncSession, *, admin: AdminAccount, initialize: bool,
    ) -> AdminRuntimeSetting | None:
        """Acquire this lock before any target-account lock in owner management."""
        await cls.seed_from_bootstrap(session)
        if initialize:
            await session.execute(
                pg_insert(AdminRuntimeSetting).values(
                    key=SUPPORT_RECIPIENT_SETTING_KEY,
                    value={"revision": 0, "admin_ids": [], "source": "owner"},
                    updated_by_admin_id=admin.id,
                ).on_conflict_do_nothing(index_elements=[AdminRuntimeSetting.key]),
            )
        return await cls.policy(session, for_update=True)

    @classmethod
    async def set_subscription(
        cls, session: AsyncSession, *, policy: AdminRuntimeSetting,
        admin: AdminAccount, account: AdminAccount, user: User, enabled: bool,
    ) -> None:
        AdminPolicy.require_permission(admin, "admins.manage")
        if admin.role != "owner":
            raise PermissionError("Only owner may manage support recipients")
        before = cls.admin_ids(policy)
        if enabled and account.id not in before and not cls.eligible(user, account):
            raise ValueError("Support recipient must be active and have support.read permission")
        selected = set(before)
        if enabled:
            selected.add(account.id)
        else:
            selected.discard(account.id)
        revision = cls.revision(policy)
        if selected == before and revision >= 1:
            return
        policy.value = {
            "revision": revision + 1,
            "admin_ids": sorted(str(item) for item in selected),
            "source": "owner",
        }
        policy.updated_by_admin_id = admin.id
        await session.flush()
