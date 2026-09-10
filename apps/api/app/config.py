"""Central configuration. All secrets come from the environment — never hardcoded.

`get_settings()` is cached; import it, don't instantiate `Settings` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ── runtime ──────────────────────────────────────────────────────────────
    env: Environment = "development"
    log_level: str = "INFO"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # ── datastores ───────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://sarathi:sarathi@localhost:5432/sarathi"
    database_url_sync: str = "postgresql+psycopg://sarathi:sarathi@localhost:5432/sarathi"
    redis_url: str = "redis://localhost:6379/0"

    # ── security ─────────────────────────────────────────────────────────────
    encryption_key: str = ""  # Fernet key; required outside dev/test
    session_secret: str = "dev-only-session-secret-change-me-please"
    session_cookie_name: str = "cp_session"
    session_ttl_hours: int = 24 * 7
    # When the web app and API are on different domains (e.g. Vercel + a Space),
    # session cookies must be SameSite=None; Secure to survive the OAuth redirect.
    cross_site_cookies: bool = False

    # ── github oauth ─────────────────────────────────────────────────────────
    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_scopes: str = "repo,read:user"

    # ── llm ──────────────────────────────────────────────────────────────────
    # `gemini` is the default provider; `anthropic` and `fake` remain available
    # behind the same LLMProvider interface.
    llm_provider: Literal["gemini", "anthropic", "fake"] = "gemini"
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    llm_default_model: str = "gemini-3.5-flash"
    llm_judge_model: str = "gemini-3.5-flash-lite"

    # ── embeddings ───────────────────────────────────────────────────────────
    embedding_provider: Literal["gemini", "fastembed", "voyage", "hash"] = "gemini"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    voyage_api_key: str = ""

    # ── agent run limits ─────────────────────────────────────────────────────
    max_tokens: int = 400_000
    max_cost_usd: float = 2.0
    max_iterations: int = 6
    max_repair_iterations: int = 3
    max_runtime_s: int = 1200
    retrieval_token_budget: int = 12_000

    # ── sandbox ──────────────────────────────────────────────────────────────
    # Hosts without a Docker daemon (e.g. a Hugging Face Space) set this true so
    # execution steps report "blocked" instead of probing a missing daemon.
    sandbox_disabled: bool = False
    sandbox_image_python: str = "sarathi/sandbox-python:latest"
    sandbox_image_node: str = "sarathi/sandbox-node:latest"
    sandbox_timeout_s: int = 120
    sandbox_memory: str = "1g"
    sandbox_cpus: float = 1.0
    sandbox_pids_limit: int = 256
    run_workspace_root: str = "/data/workspaces"
    workspace_ttl_h: int = 48

    # ── dev ──────────────────────────────────────────────────────────────────
    dev_auth_bypass: bool = False

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cookie_samesite(self) -> str:
        return "none" if self.cross_site_cookies else "lax"

    @property
    def cookie_secure(self) -> bool:
        # SameSite=None requires Secure; also secure in production.
        return self.cross_site_cookies or self.is_production

    @property
    def github_scope_list(self) -> list[str]:
        return [s.strip() for s in self.github_oauth_scopes.split(",") if s.strip()]

    @field_validator("dev_auth_bypass")
    @classmethod
    def _no_bypass_in_prod(cls, v: bool, info):  # noqa: ANN001
        if v and info.data.get("env") == "production":
            raise ValueError("DEV_AUTH_BYPASS must be false when ENV=production")
        return v

    def require_for_production(self) -> list[str]:
        """Return the list of config problems that must be fixed before prod boot."""
        problems: list[str] = []
        if not self.is_production:
            return problems
        if not self.encryption_key:
            problems.append("ENCRYPTION_KEY is required in production")
        if self.session_secret == Settings.model_fields["session_secret"].default:
            problems.append("SESSION_SECRET must be overridden in production")
        if not (self.github_client_id and self.github_client_secret):
            problems.append("GITHUB_CLIENT_ID/SECRET are required in production")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            problems.append("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            problems.append("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        if self.embedding_provider == "gemini" and not self.gemini_api_key:
            problems.append("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini")
        if self.dev_auth_bypass:
            problems.append("DEV_AUTH_BYPASS must be false in production")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
