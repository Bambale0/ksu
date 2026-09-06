from __future__ import annotations

import os
from pathlib import Path

import pytest


def _dotenv_value(name: str) -> str:
    path = Path('.env')
    if not path.is_file():
        return ''
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value.strip()
    return ''


# Integration tests use the real SQLAlchemy SessionFactory and can write hundreds
# of rows. Never let an accidental `pytest` on a production checkout inherit the
# live .env database. CI opts in explicitly next to APP_ENV=test. Keep this guard
# stdlib-only so it runs before importing the application or third-party services.
def pytest_sessionstart(session: pytest.Session) -> None:
    app_env = (os.getenv('APP_ENV') or _dotenv_value('APP_ENV') or 'development').lower()
    if app_env != 'test' or os.getenv('KSU_ALLOW_TEST_DATABASE') != '1':
        pytest.exit(
            'Refusing to run database-capable tests without APP_ENV=test and '
            'KSU_ALLOW_TEST_DATABASE=1. Use an isolated test database.',
            returncode=4,
        )
