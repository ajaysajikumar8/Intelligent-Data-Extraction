from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator, computed_field


# ==============================================================================
# ENUMS
# ==============================================================================

class Role(str, Enum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class Source(str, Enum):
    MANUAL = "MANUAL"
    API = "API"
    EMAIL = "EMAIL"
    WEBHOOK = "WEBHOOK"


class ExtractionStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNMATCHED = "UNMATCHED"


class WebhookEventType(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNMATCHED = "UNMATCHED"


# ==============================================================================
# PLAN SCHEMAS
# ==============================================================================

class PlanBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=50)
    maxExtractionsPerMonth: int | None = None
    maxTemplates: int | None = None
    maxWebhooks: int | None = None
    maxUsers: int | None = None
    priceUsdCents: int = Field(default=0, ge=0)
    isActive: bool = True


class PlanResponse(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    createdAt: datetime
    updatedAt: datetime


# ==============================================================================
# WORKSPACE SCHEMAS
# ==============================================================================

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")


class WorkspaceUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    apiKey: str
    planId: str
    createdAt: datetime


class WorkspaceRotateApiKeyResponse(BaseModel):
    apiKey: str
    message: str = "API key regenerated successfully."


class WorkspaceWithPlanResponse(WorkspaceResponse):
    plan: PlanResponse


# ==============================================================================
# USER & AUTH SCHEMAS
# ==============================================================================

class UserSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=100)
    workspaceName: str | None = Field(default=None, max_length=100)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    name: str | None = None
    googleId: str | None = None
    avatarUrl: str | None = None
    workspaceId: str
    role: Role
    isActive: bool
    createdAt: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    workspace: WorkspaceResponse


class TokenPayload(BaseModel):
    sub: str
    workspace_id: str
    role: Role
    exp: int | None = None



# ==============================================================================
# TEMPLATE SCHEMAS
# ==============================================================================

class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    schema: dict[str, Any] = Field(..., description="Target JSON schema dict for extraction target")


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    schema: dict[str, Any] | None = None
    isActive: bool | None = None


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    workspaceId: str
    name: str
    description: str | None = None
    extractionSchema: dict[str, Any] = Field(..., alias="schema")
    version: int
    isActive: bool
    createdAt: datetime
    updatedAt: datetime

    @computed_field  # type: ignore[misc]
    @property
    def fieldCount(self) -> int:
        """Dynamically derived top-level key count in extraction schema."""
        return len(self.extractionSchema.keys()) if isinstance(self.extractionSchema, dict) else 0


# ==============================================================================
# DOCUMENT LOG SCHEMAS
# ==============================================================================

class DocumentLogCreate(BaseModel):
    source: Source = Source.MANUAL
    rawInput: str | None = None
    rawInputUrl: str | None = None
    fileName: str | None = None
    mimeType: str | None = None

    @model_validator(mode="after")
    def validate_input_sources(self) -> "DocumentLogCreate":
        if not self.rawInput and not self.rawInputUrl:
            raise ValueError("Either rawInput or rawInputUrl must be provided.")
        if self.rawInput and self.rawInputUrl:
            raise ValueError("rawInput and rawInputUrl are mutually exclusive.")
        return self


class DocumentLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspaceId: str
    templateId: str | None = None
    userId: str | None = None
    source: Source
    status: ExtractionStatus
    rawInput: str | None = None
    rawInputUrl: str | None = None
    fileName: str | None = None
    mimeType: str | None = None
    extractedJson: dict[str, Any] | list[Any] | None = None
    validationErrors: list[Any] | dict[str, Any] | None = None
    processingMs: int | None = None
    createdAt: datetime


# ==============================================================================
# WEBHOOK ENDPOINT SCHEMAS
# ==============================================================================

class WebhookCreate(BaseModel):
    url: str = Field(..., pattern=r"^https?://")
    description: str | None = Field(default=None, max_length=200)
    eventTypes: list[WebhookEventType] = Field(default_factory=list)
    templateIds: list[str] = Field(default_factory=list)


class WebhookUpdate(BaseModel):
    url: str | None = Field(default=None, pattern=r"^https?://")
    description: str | None = Field(default=None, max_length=200)
    eventTypes: list[WebhookEventType] | None = None
    templateIds: list[str] | None = None
    isActive: bool | None = None


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspaceId: str
    url: str
    secret: str
    description: str | None = None
    eventTypes: list[WebhookEventType]
    templateIds: list[str]
    isActive: bool
    lastPingAt: datetime | None = None
    failureCount: int
    createdAt: datetime
    updatedAt: datetime
