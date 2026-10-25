from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    source_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(String(300), default="Unbekannt")
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    mileage: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(180), nullable=True)
    make: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(180), nullable=True)
    body_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    engine: Mapped[str | None] = mapped_column(String(180), nullable=True)
    power_kw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    three_point_belt: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dry_status: Mapped[str] = mapped_column(String(40), default="unknown")
    repair_level: Mapped[str] = mapped_column(String(30), default="unknown")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    score_explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    inactive_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    images: Mapped[list["ListingImage"]] = relationship(back_populates="listing", cascade="all, delete-orphan")
    prices: Mapped[list["PriceHistory"]] = relationship(back_populates="listing", cascade="all, delete-orphan")
    captures: Mapped[list["CaptureSnapshot"]] = relationship(back_populates="listing", cascade="all, delete-orphan")
    vehicle_identity: Mapped["VehicleIdentity | None"] = relationship(back_populates="listing", cascade="all, delete-orphan", uselist=False)
    signals: Mapped["ListingSignals | None"] = relationship(back_populates="listing", cascade="all, delete-orphan", uselist=False)
    technical_data: Mapped["ListingTechnicalData | None"] = relationship(back_populates="listing", cascade="all, delete-orphan", uselist=False)
    import_state: Mapped["ImportState | None"] = relationship(back_populates="listing", cascade="all, delete-orphan", uselist=False)

class ListingImage(Base):
    __tablename__ = "listing_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    remote_url: Mapped[str] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    listing: Mapped[Listing] = relationship(back_populates="images")

class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    price: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    listing: Mapped[Listing] = relationship(back_populates="prices")

class CaptureSnapshot(Base):
    __tablename__ = "capture_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    page_title: Mapped[str] = mapped_column(Text, default="")
    meta_description: Mapped[str] = mapped_column(Text, default="")
    page_text: Mapped[str] = mapped_column(Text, default="")
    structured_data: Mapped[str] = mapped_column(Text, default="")
    image_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    listing: Mapped[Listing] = relationship(back_populates="captures")

class VehicleIdentity(Base):
    __tablename__ = "vehicle_identities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), unique=True, index=True)
    base_make: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    coachbuilder: Mapped[str | None] = mapped_column(String(120), nullable=True)
    coach_model: Mapped[str | None] = mapped_column(String(180), nullable=True)
    engine_text: Mapped[str | None] = mapped_column(String(180), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    listing: Mapped[Listing] = relationship(back_populates="vehicle_identity")

class ListingSignals(Base):
    __tablename__ = "listing_signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), unique=True, index=True)
    portal_listing_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    listed_at_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    seller_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    seller_active_since: Mapped[str | None] = mapped_column(String(80), nullable=True)
    seller_ads_online: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_ads_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_badges: Mapped[str | None] = mapped_column(Text, nullable=True)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watchers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dealer_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    raw_signal_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    listing: Mapped[Listing] = relationship(back_populates="signals")

class ListingTechnicalData(Base):
    __tablename__ = "listing_technical_data"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), unique=True, index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    listing: Mapped[Listing] = relationship(back_populates="technical_data")

class ImportState(Base):
    __tablename__ = "import_states"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    listing: Mapped[Listing] = relationship(back_populates="import_state")

class SearchProfile(Base):
    __tablename__ = "search_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="Unsere Wohnmobilsuche")
    prompt: Mapped[str] = mapped_column(Text, default="")
    max_price: Mapped[int] = mapped_column(Integer, default=11000)
    max_distance_km: Mapped[int] = mapped_column(Integer, default=300)
    min_year: Mapped[int] = mapped_column(Integer, default=1988)
    max_mileage: Mapped[int] = mapped_column(Integer, default=260000)
    max_weight_kg: Mapped[int] = mapped_column(Integer, default=3500)
    require_alkoven: Mapped[bool] = mapped_column(Boolean, default=True)
    require_three_point_belt: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_engine: Mapped[str] = mapped_column(String(100), default="2.5 TD")
    repair_tolerance: Mapped[str] = mapped_column(String(30), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
