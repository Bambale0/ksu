"""Validated database-backed login issuance policy, shared with admin control plane."""
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminRuntimeSetting
from app.services.browser_approval import ApprovalLimits

SETTING_KEY = "browser_approval_limits"
_DEFAULTS = ApprovalLimits()


class BrowserApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    browser_limit: int = Field(default=_DEFAULTS.browser_limit, ge=1, le=100, strict=True)
    network_limit: int = Field(default=_DEFAULTS.network_limit, ge=1, le=100000, strict=True)
    window_seconds: int = Field(default=_DEFAULTS.window_seconds, ge=60, le=3600, strict=True)
    revision: int = Field(default=_DEFAULTS.revision, ge=1, strict=True)

    def limits(self) -> ApprovalLimits:
        return ApprovalLimits(**self.model_dump())


async def configured_browser_approval(session: AsyncSession) -> BrowserApprovalPolicy:
    row = await session.get(AdminRuntimeSetting, SETTING_KEY)
    return BrowserApprovalPolicy.model_validate(row.value) if row is not None else BrowserApprovalPolicy()
