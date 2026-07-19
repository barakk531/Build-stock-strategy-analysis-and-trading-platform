from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: Literal["ok", "unavailable"]
    # False = ADMIN_API_KEY not configured (development mode, unprotected).
    auth_required: bool = False
    timestamp: datetime
