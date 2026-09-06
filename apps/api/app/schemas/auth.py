from __future__ import annotations

import uuid

from app.models.enums import AutonomyLevel
from app.schemas.common import ORMModel


class Me(ORMModel):
    id: uuid.UUID
    login: str
    name: str | None
    avatar_url: str | None
    default_autonomy: AutonomyLevel
    csrf_token: str
    auth_mode: str  # "github" | "dev"
