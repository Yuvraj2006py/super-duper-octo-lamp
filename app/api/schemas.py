from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import JobStatus


class LoginRequest(BaseModel):
    api_key: str


class LoginResponse(BaseModel):
    token: str
    user_id: str


class AllowedClaim(BaseModel):
    claim: str
    metric: str | None = None
    source: str | None = None


class UserProfile(BaseModel):
    personal_info: dict[str, Any]
    education: list[dict[str, Any]] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    allowed_claims: list[AllowedClaim] = Field(default_factory=list)
    external_experiences: list[dict[str, Any] | str] = Field(default_factory=list)
    application_assets: dict[str, Any] = Field(default_factory=dict)
    internship_preferences: dict[str, Any] = Field(default_factory=dict)


class JobImportJsonRequest(BaseModel):
    source_name: str = "manual-json"
    jobs: list[dict[str, Any]]


class JobImportJsonFileRequest(BaseModel):
    file_path: str = "/data/jobs_sample.json"


class JobImportRssRequest(BaseModel):
    source_name: str
    feed_url: str
    terms_url: str | None = None
    automation_allowed: bool = True


class JobImportUrlRequest(BaseModel):
    source_name: str = "manual-url"
    url: str
    external_id: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    application_questions: list[str] = Field(default_factory=list)


class JobResponse(BaseModel):
    id: UUID
    source_id: int
    external_id: str
    url: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    seniority: str | None = None
    platform: str | None = None
    status: JobStatus
    score_total: float | None = None
    score_breakdown: dict[str, Any] | None = None
    raw_payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ApplicationFormFieldResponse(BaseModel):
    id: int
    job_id: UUID
    field_key: str
    label: str | None = None
    type: str
    required: bool
    platform: str
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineRunRequest(BaseModel):
    top_n: int = 3
    status_filter: JobStatus = JobStatus.DISCOVERED
    dry_run: bool = False


class PipelineRunResponse(BaseModel):
    processed: int
    results: list[dict[str, Any]]


class ApprovalActionRequest(BaseModel):
    reason: str | None = None


class ApplicationResponse(BaseModel):
    id: UUID
    user_id: UUID
    job_id: UUID
    status: JobStatus
    verification_passed: bool | None = None
    verification_report: dict[str, Any] | None = None
    claims_table: list[dict[str, Any]] | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SubmissionPacketResponse(BaseModel):
    id: int
    application_id: UUID
    attempt_no: int
    status: str
    response_url: str | None = None
    block_reason: str | None = None
    payload: dict[str, Any]
    created_at: datetime
    submitted_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuditEventResponse(BaseModel):
    id: int
    actor_type: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
