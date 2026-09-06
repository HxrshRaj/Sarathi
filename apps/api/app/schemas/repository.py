from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import IndexStatus
from app.schemas.common import ORMModel


class GithubRepoOut(BaseModel):
    github_repo_id: int
    full_name: str
    default_branch: str
    private: bool
    clone_url: str
    updated_at: str
    connected: bool = False


class ConnectRepoIn(BaseModel):
    github_repo_id: int


class RepositoryVersionOut(ORMModel):
    id: uuid.UUID
    branch: str
    commit_sha: str
    status: IndexStatus
    file_count: int
    chunk_count: int
    index_error: str | None
    indexed_at: datetime | None
    created_at: datetime


class RepositoryOut(ORMModel):
    id: uuid.UUID
    github_repo_id: int
    full_name: str
    default_branch: str
    private: bool
    created_at: datetime
    latest_version: RepositoryVersionOut | None = None


class IndexRepoIn(BaseModel):
    branch: str = Field(min_length=1, max_length=255)
