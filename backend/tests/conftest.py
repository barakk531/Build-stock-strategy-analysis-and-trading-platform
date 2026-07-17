import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# Deterministic settings for tests: no scheduler, explicit environment.
# Env vars outrank the .env file, so this wins regardless of local config.
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "test"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
