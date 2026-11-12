"""Content API shapes (CNT-01..06).

Server-owned fields a client echoes back are dropped, never applied; any other unknown
field is 400.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.phone import normalize_phone
from app.db.models.catalog import SLUG_PATTERN
from app.db.models.content import (
    MAX_CONTACT_TEXT_LENGTH,
    MAX_FAQ_ANSWER_LENGTH,
    MAX_PAGE_BODY_LENGTH,
    MAX_SECTION_PRODUCTS,
    MAX_SECTION_TEXT_LENGTH,
    ContactStatus,
    PageStatus,
    ProductSource,
    SectionType,
    TargetType,
)
from app.modules.auth.schemas import EMAIL_MAX_LENGTH
from app.modules.catalog.schemas import CategorySummary, ProductCard
from app.modules.content.markdown import check_markdown

_SYSTEM_FIELDS: Final = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "published_at",
        "created_by",
        "updated_by",
        # Built by the server from the media ids.
        "image_url",
        "mobile_image_url",
    }
)
# Printable only: no control characters (a NUL would fail in PostgreSQL).
_NO_CONTROL: Final = r"^[^\x00-\x1f\x7f]+$"

Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
PageTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=_NO_CONTROL)
]
PageBody = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_PAGE_BODY_LENGTH),
    AfterValidator(check_markdown),
]


def drop_system_fields(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: value for key, value in data.items() if key not in _SYSTEM_FIELDS}
    return data


def require_some_non_null(model: BaseModel, nullable: frozenset[str] = frozenset()) -> None:
    """A PATCH changes at least one field and clears only the nullable ones."""
    sent = model.model_fields_set
    if not sent:
        raise ValueError("at least one field is required")
    nulls = sorted(name for name in sent - nullable if getattr(model, name) is None)
    if nulls:
        raise ValueError(f"must not be null: {', '.join(nulls)}")


class CreatePageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    title: PageTitle
    body: PageBody
    status: PageStatus = PageStatus.DRAFT

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)


class UpdatePageRequest(BaseModel):
    """Sent fields change; the slug is fixed at creation, so sending it is a 400."""

    model_config = ConfigDict(extra="forbid")

    title: PageTitle | None = None
    body: PageBody | None = None
    status: PageStatus | None = None

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)

    @model_validator(mode="after")
    def _fields(self) -> UpdatePageRequest:
        require_some_non_null(self)
        return self


class AdminPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    title: str
    body: str
    status: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublicPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    body: str
    updated_at: datetime


# --- FAQ (CNT-05) ------------------------------------------------------------------------


MAX_DISPLAY_ORDER: Final = 1_000_000

DisplayOrder = Annotated[int, Field(strict=True, ge=0, le=MAX_DISPLAY_ORDER)]
FaqGroup = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=_NO_CONTROL)
]
FaqQuestion = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500, pattern=_NO_CONTROL)
]
FaqAnswer = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_FAQ_ANSWER_LENGTH),
    AfterValidator(check_markdown),
]


class CreateFaqRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_title: FaqGroup
    question: FaqQuestion
    answer: FaqAnswer
    display_order: DisplayOrder = 0
    is_published: StrictBool = False

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)


class UpdateFaqRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_title: FaqGroup | None = None
    question: FaqQuestion | None = None
    answer: FaqAnswer | None = None
    display_order: DisplayOrder | None = None
    is_published: StrictBool | None = None

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)

    @model_validator(mode="after")
    def _fields(self) -> UpdateFaqRequest:
        require_some_non_null(self)
        return self


class AdminFaqResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    group_title: str
    question: str
    answer: str
    display_order: int
    is_published: bool
    created_at: datetime
    updated_at: datetime


class PublicFaqItem(BaseModel):
    id: UUID
    question: str
    answer: str


class PublicFaqGroup(BaseModel):
    title: str
    items: list[PublicFaqItem]


class PublicFaqResponse(BaseModel):
    groups: list[PublicFaqGroup]


# --- contact form (CNT-06) ----------------------------------------------------------------


_CONTACT_SYSTEM_FIELDS: Final = frozenset(
    {"id", "status", "user_id", "ip", "handled_by", "internal_note", "created_at", "updated_at"}
)
# Newlines are text; every other control character is refused.
_MULTILINE: Final = r"^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+$"

ContactName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=_NO_CONTROL)
]
ContactSubject = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=_NO_CONTROL)
]
ContactText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_CONTACT_TEXT_LENGTH, pattern=_MULTILINE
    ),
]


class ContactRequest(BaseModel):
    """Plain text, shown as text; server-owned fields a client sends are dropped."""

    model_config = ConfigDict(extra="forbid")

    name: ContactName
    mobile: str = Field(min_length=1, max_length=32)
    email: str | None = None
    subject: ContactSubject
    message: ContactText

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in _CONTACT_SYSTEM_FIELDS}
        return data

    @field_validator("mobile")
    @classmethod
    def _normalize_mobile(cls, value: str) -> str:
        # InvalidPhoneError is a ValueError, so an invalid number becomes a 400.
        return normalize_phone(value)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        email = value.strip()
        if len(email) > EMAIL_MAX_LENGTH:
            raise ValueError(f"must be at most {EMAIL_MAX_LENGTH} characters")
        try:
            normalized = validate_email(email, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise ValueError("must be a valid email address") from exc
        return normalized.lower()


class UpdateContactRequest(BaseModel):
    """Null clears the internal note; the status moves only along the allowed transitions."""

    model_config = ConfigDict(extra="forbid")

    status: ContactStatus | None = None
    internal_note: ContactText | None = None

    @model_validator(mode="after")
    def _fields(self) -> UpdateContactRequest:
        require_some_non_null(self, frozenset({"internal_note"}))
        return self


class AdminContactSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    mobile: str = Field(validation_alias="phone")
    subject: str
    status: str
    created_at: datetime


class AdminContactDetail(AdminContactSummary):
    user_id: UUID | None
    email: str | None
    message: str
    internal_note: str | None
    handled_by: UUID | None
    updated_at: datetime


# --- home page (CNT-01) -------------------------------------------------------------------


class HomeTarget(BaseModel):
    type: str
    slug: str


class HomeItem(BaseModel):
    """One entry; ``product`` is the listing card, ``category`` the category summary.

    A banner (hero sections) also has ``subtitle``, ``mobile_image_url`` and ``target``.
    """

    title: str | None = None
    subtitle: str | None = None
    body: str | None = None
    icon_key: str | None = None
    image_url: str | None = None
    mobile_image_url: str | None = None
    target: HomeTarget | None = None
    product: ProductCard | None = None
    category: CategorySummary | None = None


class HomeSectionOut(BaseModel):
    # Null for the default layout shown when no section is active.
    id: UUID | None
    type: str
    title: str
    subtitle: str | None
    layout_variant: str | None
    target: HomeTarget | None
    items: list[HomeItem]


class HomeResponse(BaseModel):
    sections: list[HomeSectionOut]
    generated_at: datetime


# --- admin home sections (CNT-02) ---------------------------------------------------------


MAX_SECTION_ITEMS: Final = 50

SectionTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=_NO_CONTROL)
]
SectionSubtitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300, pattern=_NO_CONTROL)
]
ShortKey = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50, pattern=_NO_CONTROL)
]
SectionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SECTION_TEXT_LENGTH),
    AfterValidator(check_markdown),
]
ProductLimit = Annotated[int, Field(strict=True, ge=1, le=MAX_SECTION_PRODUCTS)]
_SECTION_NULLABLE: Final = frozenset(
    {
        "subtitle",
        "layout_variant",
        "starts_at",
        "ends_at",
        "target_id",
        "product_source",
        "source_category_id",
    }
)


class SectionItemIn(BaseModel):
    """What an item holds depends on the section type (checked with the whole section)."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID | None = None
    category_id: UUID | None = None
    title_override: SectionTitle | None = None
    body: SectionText | None = None
    image_media_id: UUID | None = None
    icon_key: ShortKey | None = None
    is_active: StrictBool = True

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)


class CreateSectionRequest(BaseModel):
    """Links are internal only (D41): a URL field or another target type is a 400."""

    model_config = ConfigDict(extra="forbid")

    type: SectionType
    title: SectionTitle
    subtitle: SectionSubtitle | None = None
    layout_variant: ShortKey | None = None
    display_order: DisplayOrder
    is_active: StrictBool = True
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    target_type: TargetType = TargetType.NONE
    target_id: UUID | None = None
    product_source: ProductSource | None = None
    source_category_id: UUID | None = None
    product_limit: ProductLimit = 12
    items: list[SectionItemIn] = Field(default_factory=list, max_length=MAX_SECTION_ITEMS)

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)


class UpdateSectionRequest(BaseModel):
    """Sent fields change; sent ``items`` replace the whole list."""

    model_config = ConfigDict(extra="forbid")

    type: SectionType | None = None
    title: SectionTitle | None = None
    subtitle: SectionSubtitle | None = None
    layout_variant: ShortKey | None = None
    display_order: DisplayOrder | None = None
    is_active: StrictBool | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    target_type: TargetType | None = None
    target_id: UUID | None = None
    product_source: ProductSource | None = None
    source_category_id: UUID | None = None
    product_limit: ProductLimit | None = None
    items: list[SectionItemIn] | None = Field(default=None, max_length=MAX_SECTION_ITEMS)

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)

    @model_validator(mode="after")
    def _fields(self) -> UpdateSectionRequest:
        require_some_non_null(self, _SECTION_NULLABLE)
        return self


class AdminSectionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID | None
    category_id: UUID | None
    title_override: str | None
    body: str | None
    image_media_id: UUID | None
    icon_key: str | None
    is_active: bool


class AdminSectionResponse(BaseModel):
    id: UUID
    type: str
    title: str
    subtitle: str | None
    layout_variant: str | None
    display_order: int
    is_active: bool
    starts_at: datetime | None
    ends_at: datetime | None
    target_type: str
    target_id: UUID | None
    product_source: str | None
    source_category_id: UUID | None
    product_limit: int
    created_at: datetime
    updated_at: datetime
    items: list[AdminSectionItem]


# --- banners (CNT-03) ---------------------------------------------------------------------


_BANNER_NULLABLE: Final = frozenset(
    {"subtitle", "mobile_image_media_id", "target_id", "starts_at", "ends_at"}
)


class CreateBannerRequest(BaseModel):
    """Links are internal only (D41): a URL field or another target type is a 400."""

    model_config = ConfigDict(extra="forbid")

    title: SectionTitle
    subtitle: SectionSubtitle | None = None
    image_media_id: UUID
    mobile_image_media_id: UUID | None = None
    target_type: TargetType = TargetType.NONE
    target_id: UUID | None = None
    display_order: DisplayOrder = 0
    is_active: StrictBool = True
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)


class UpdateBannerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: SectionTitle | None = None
    subtitle: SectionSubtitle | None = None
    image_media_id: UUID | None = None
    mobile_image_media_id: UUID | None = None
    target_type: TargetType | None = None
    target_id: UUID | None = None
    display_order: DisplayOrder | None = None
    is_active: StrictBool | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)

    @model_validator(mode="after")
    def _fields(self) -> UpdateBannerRequest:
        require_some_non_null(self, _BANNER_NULLABLE)
        return self


class AdminBannerResponse(BaseModel):
    id: UUID
    title: str
    subtitle: str | None
    image_media_id: UUID
    image_url: str | None
    mobile_image_media_id: UUID | None
    mobile_image_url: str | None
    target_type: str
    target_id: UUID | None
    display_order: int
    is_active: bool
    starts_at: datetime | None
    ends_at: datetime | None
    created_at: datetime
    updated_at: datetime
