from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.services.browser_approval_policy import BrowserApprovalPolicy, configured_browser_approval


@pytest.mark.parametrize("fields", [
    {"browser_limit": 0}, {"network_limit": 100001}, {"window_seconds": 59},
    {"revision": 0}, {"browser_limit": "5"}, {"unknown": 1},
])
def test_approval_limits_reject_invalid_or_unknown_values(fields):
    with pytest.raises(ValidationError):
        BrowserApprovalPolicy(**fields)


@pytest.mark.asyncio
async def test_runtime_approval_policy_is_loaded_without_restart():
    session = AsyncMock()
    session.get.return_value = None
    defaults = await configured_browser_approval(session)
    assert defaults.limits().browser_limit == 5
    session.get.return_value = type("Row", (), {
        "value": {"browser_limit": 9, "network_limit": 500, "window_seconds": 120, "revision": 2},
    })()
    effective = await configured_browser_approval(session)
    assert effective.limits().browser_limit == 9
    assert effective.limits().revision == 2
