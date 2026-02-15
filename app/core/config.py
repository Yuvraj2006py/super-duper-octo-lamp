from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Job Application Assistant"
    environment: str = "dev"
    debug: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/job_assistant"
    redis_url: str = "redis://redis:6379/0"

    local_api_key: str = "change-me"
    secret_key: str = "dev-secret"
    token_ttl_seconds: int = 8 * 60 * 60

    embedding_provider: str = "mock"
    embedding_model_name: str = "mock-embed-v1"
    embedding_dim: int = 256
    embedding_cache_dir: Path = Path("/workspace/.cache/fastembed")
    llm_provider: str = "mock"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 400
    llm_timeout_seconds: int = 45

    ingestion_rate_limit: int = 60
    drafting_rate_limit: int = 120
    rate_limit_window_seconds: int = 60
    max_applications_per_company: int = 2

    output_dir: Path = Path("/output")
    data_dir: Path = Path("/data")
    template_dir: Path = Path("app/templates")
    form_storage_state_path: Path = Path("secrets/workday_state.json")
    form_fetch_timeout_ms: int = 120000
    form_fetch_wait_ms: int = 2000
    form_browser_headless: bool = True
    form_submit_mode: str = "mock"
    form_submit_retries: int = 2
    # Safety default: never finalize irreversible submits unless explicitly enabled.
    # The agent should still be able to fetch/catalog fields and fill drafts for review.
    form_submit_dry_run: bool = True
    form_allow_final_submit: bool = False
    form_max_steps: int = 12

    # Local file assets used for ATS upload fields (inside containers: mounted at /workspace).
    resume_pdf_path: Path = Path("resume/resume.pdf")
    transcript_pdf_path: Path = Path("resume/transcript.pdf")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
