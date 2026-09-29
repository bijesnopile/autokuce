"""All SQLAlchemy models (specification chapter 6).

Enum-like columns are plain strings with the allowed values defined as
constants below (no DB enum types -> simpler migrations). All datetimes are
naive UTC (see `app.database.utcnow`).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow

# ---------------------------------------------------------------------------
# String constants ("enums")
# ---------------------------------------------------------------------------
ROLE_SUPERADMIN = "superadmin"
ROLE_OWNER = "owner"
ROLE_SALESPERSON = "salesperson"
ROLES = (ROLE_SUPERADMIN, ROLE_OWNER, ROLE_SALESPERSON)

TOKEN_INVITE = "invite"
TOKEN_RESET = "reset"

VEHICLE_TYPES = ("car", "van", "motorcycle", "camper", "truck")

CONDITION_NEW = "new"
CONDITION_USED = "used"
CONDITIONS = (CONDITION_NEW, CONDITION_USED)

STATUS_DRAFT = "draft"
STATUS_ACTIVE = "active"
STATUS_RESERVED = "reserved"
STATUS_SOLD = "sold"
STATUS_ARCHIVED = "archived"
VEHICLE_STATUSES = (STATUS_DRAFT, STATUS_ACTIVE, STATUS_RESERVED, STATUS_SOLD, STATUS_ARCHIVED)

TAX_TYPES = ("pdv", "marza", "bez_pdv")

INQUIRY_VEHICLE = "vehicle"
INQUIRY_GENERAL = "general"
INQUIRY_VIEWING = "viewing"
INQUIRY_FINANCING = "financing"
INQUIRY_TYPES = (INQUIRY_VEHICLE, INQUIRY_GENERAL, INQUIRY_VIEWING, INQUIRY_FINANCING)

INQUIRY_NEW = "new"
INQUIRY_CONTACTED = "contacted"
INQUIRY_CLOSED = "closed"
INQUIRY_STATUSES = (INQUIRY_NEW, INQUIRY_CONTACTED, INQUIRY_CLOSED)

SUB_PENDING = "pending"
SUB_CONFIRMED = "confirmed"
SUB_UNSUBSCRIBED = "unsubscribed"
SUBSCRIBER_STATUSES = (SUB_PENDING, SUB_CONFIRMED, SUB_UNSUBSCRIBED)

CAMPAIGN_DRAFT = "draft"
CAMPAIGN_SENDING = "sending"
CAMPAIGN_SENT = "sent"

DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"

PAGE_SLUGS = ("o-nama", "usluge", "privatnost", "kolacici", "uvjeti")


# ---------------------------------------------------------------------------
# Users and authentication
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(20), default=ROLE_SALESPERSON)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # TOTP secret, Fernet-encrypted with a key derived from SECRET_KEY.
    totp_secret: Mapped[str | None] = mapped_column(String(255))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Last accepted TOTP time step (replay protection within the validity window).
    totp_last_step: Mapped[int | None] = mapped_column(Integer)
    # List of Argon2 hashes of one-time recovery codes.
    recovery_codes: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.id} {self.role}>"


class UserSession(Base):
    """Server-side admin session (table `sessions`)."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


class AuthToken(Base):
    """One-time tokens for invitations and password resets (only the hash is stored)."""

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship()


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
class Make(Base):
    __tablename__ = "makes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    models: Mapped[list[VehicleModel]] = relationship(
        back_populates="make", order_by="VehicleModel.name", passive_deletes=True
    )


class VehicleModel(Base):
    __tablename__ = "vehicle_models"
    __table_args__ = (UniqueConstraint("make_id", "slug", name="uq_vehicle_models_make_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    make_id: Mapped[int] = mapped_column(ForeignKey("makes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(80))
    # NULL = model is valid for all vehicle types.
    vehicle_type: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    make: Mapped[Make] = relationship(back_populates="models")


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------
class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        Index("ix_vehicles_status_type", "status", "vehicle_type"),
        Index("ix_vehicles_status_published", "status", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    vehicle_type: Mapped[str] = mapped_column(String(20), index=True)
    make_id: Mapped[int] = mapped_column(ForeignKey("makes.id"), index=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_models.id"), index=True)
    variant: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(250), default="")
    condition: Mapped[str] = mapped_column(String(10), default=CONDITION_USED)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_DRAFT, index=True)

    year: Mapped[int | None] = mapped_column(Integer, index=True)
    first_registration: Mapped[date | None] = mapped_column(Date)  # month precision (day=1)
    mileage_km: Mapped[int | None] = mapped_column(Integer, index=True)

    price_eur: Mapped[int | None] = mapped_column(Integer, index=True)
    price_old_eur: Mapped[int | None] = mapped_column(Integer)
    price_on_request: Mapped[bool] = mapped_column(Boolean, default=False)
    tax_type: Mapped[str] = mapped_column(String(10), default="pdv")

    fuel: Mapped[str | None] = mapped_column(String(20), index=True)
    power_kw: Mapped[int | None] = mapped_column(Integer)
    power_hp: Mapped[int | None] = mapped_column(Integer)
    engine_ccm: Mapped[int | None] = mapped_column(Integer)
    transmission: Mapped[str | None] = mapped_column(String(20), index=True)
    drive: Mapped[str | None] = mapped_column(String(20))
    color: Mapped[str | None] = mapped_column(String(30))
    color_metallic: Mapped[bool] = mapped_column(Boolean, default=False)
    doors: Mapped[int | None] = mapped_column(Integer)
    seats: Mapped[int | None] = mapped_column(Integer)
    euro_norm: Mapped[str | None] = mapped_column(String(20))
    fuel_consumption_l100: Mapped[float | None] = mapped_column(Float)
    co2_g_km: Mapped[int | None] = mapped_column(Integer)
    registered_until: Mapped[date | None] = mapped_column(Date)
    first_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    service_book: Mapped[bool] = mapped_column(Boolean, default=False)
    warranty_months: Mapped[int | None] = mapped_column(Integer)
    # Admin only — never rendered on public pages.
    vin: Mapped[str | None] = mapped_column(String(32))

    description: Mapped[str] = mapped_column(Text, default="")  # sanitized HTML
    equipment: Mapped[list] = mapped_column(JSON, default=list)  # list of equipment codes
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)  # type-specific fields
    featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    views_total: Mapped[int] = mapped_column(Integer, default=0)
    video_url: Mapped[str | None] = mapped_column(String(300))

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime)

    make: Mapped[Make] = relationship()
    model: Mapped[VehicleModel | None] = relationship()
    images: Mapped[list[VehicleImage]] = relationship(
        back_populates="vehicle",
        order_by="[VehicleImage.sort_order, VehicleImage.id]",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def main_image(self) -> VehicleImage | None:
        return self.images[0] if self.images else None


class VehicleSlugHistory(Base):
    __tablename__ = "vehicle_slug_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    old_slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VehicleImage(Base):
    __tablename__ = "vehicle_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    # Base key; variants are stored as f"{file_key}_{400|1000|1600}.webp".
    file_key: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    alt: Mapped[str] = mapped_column(String(250), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    vehicle: Mapped[Vehicle] = relationship(back_populates="images")


class VehicleView(Base):
    """Daily view counter per vehicle (unique pair vehicle_id + date)."""

    __tablename__ = "vehicle_views"

    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class ContactClick(Base):
    """Daily count of WhatsApp/Viber button clicks per vehicle and channel (no personal data).

    `vehicle_id` is NULL for buttons outside a vehicle ad (contact page)."""

    __tablename__ = "contact_clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(20))
    date: Mapped[date] = mapped_column(Date, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class FeedAccess(Base):
    """Last download of each portal feed (shown on /admin/feed; no personal data)."""

    __tablename__ = "feed_access"

    portal: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_format: Mapped[str] = mapped_column(String(4), default="xml")
    count: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# Inquiries (mini CRM)
# ---------------------------------------------------------------------------
class Inquiry(Base):
    __tablename__ = "inquiries"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Plain string: new inquiry types (test drive, financing, trade-in...) need no migration.
    type: Mapped[str] = mapped_column(String(30), default=INQUIRY_GENERAL, index=True)
    vehicle_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text, default="")
    preferred_date: Mapped[datetime | None] = mapped_column(DateTime)
    # Viewing confirmed by the dealer (naive UTC); the .ics update keeps the same UID.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Free-form extra fields for future inquiry types (JSON, no schema change needed).
    extra: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default=INQUIRY_NEW, index=True)
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    consent_ip: Mapped[str | None] = mapped_column(String(64))
    consent_user_agent: Mapped[str | None] = mapped_column(String(300))
    consent_policy_version: Mapped[str | None] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime)  # first "contacted"
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    vehicle: Mapped[Vehicle | None] = relationship()
    assignee: Mapped[User | None] = relationship()
    notes: Mapped[list[InquiryNote]] = relationship(
        back_populates="inquiry",
        order_by="InquiryNote.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class InquiryNote(Base):
    __tablename__ = "inquiry_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(
        ForeignKey("inquiries.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    inquiry: Mapped[Inquiry] = relationship(back_populates="notes")
    user: Mapped[User | None] = relationship()


# ---------------------------------------------------------------------------
# Newsletter
# ---------------------------------------------------------------------------
class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL after unsubscribe (anonymized); the hash stays as a suppression entry.
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=SUB_PENDING, index=True)
    confirm_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    unsubscribe_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    confirm_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    consent_ip: Mapped[str | None] = mapped_column(String(64))
    consent_user_agent: Mapped[str | None] = mapped_column(String(300))
    consent_policy_version: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(30))  # footer | home | vehicle | manual
    manual_consent_note: Mapped[str | None] = mapped_column(String(300))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(120))
    body_html: Mapped[str] = mapped_column(Text, default="")  # sanitized
    status: Mapped[str] = mapped_column(String(20), default=CAMPAIGN_DRAFT, index=True)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    deliveries: Mapped[list[CampaignDelivery]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", passive_deletes=True
    )


class CampaignDelivery(Base):
    __tablename__ = "campaign_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "subscriber_id", name="uq_campaign_deliveries_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    subscriber_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscribers.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="deliveries")


# ---------------------------------------------------------------------------
# Settings, pages, logs
# ---------------------------------------------------------------------------
class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    body_html: Mapped[str] = mapped_column(Text, default="")  # sanitized
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    # Never contains customer personal data (only IDs, hashes, counts, field names).
    details: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[User | None] = relationship()


class EmailLog(Base):
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA-256, never the address
    template: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
