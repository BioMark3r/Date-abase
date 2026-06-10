import json as _json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .database import Base


class DateEntry(Base):
    __tablename__ = "dates"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    pre_date_activities = Column(Text, nullable=True)
    date_datetime = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=True)
    location_name = Column(String(300), nullable=True)
    location_lat = Column(Float, nullable=True)
    location_lon = Column(Float, nullable=True)
    what_we_did = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    rating = Column(Integer, default=5)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    images = relationship(
        "DateImage",
        back_populates="date",
        cascade="all, delete-orphan",
        order_by="DateImage.uploaded_at",
    )
    locations = relationship(
        "DateLocation",
        back_populates="date",
        cascade="all, delete-orphan",
        order_by="DateLocation.sort_order",
    )

    def to_dict(self):
        locs = []
        try:
            locs = [
                {"name": l.name, "lat": l.lat, "lon": l.lon,
                 "label": l.label, "sort_order": l.sort_order}
                for l in (self.locations or [])
            ]
        except Exception:
            pass
        imgs = []
        try:
            imgs = [
                {"filename": i.filename, "caption": i.caption}
                for i in (self.images or [])
            ]
        except Exception:
            pass
        return {
            "id": self.id,
            "title": self.title,
            "pre_date_activities": self.pre_date_activities,
            "date_datetime": self.date_datetime.isoformat() if self.date_datetime else None,
            "duration_minutes": self.duration_minutes,
            # legacy single-location fields kept for backward compat
            "location_name": self.location_name,
            "location_lat": self.location_lat,
            "location_lon": self.location_lon,
            # new multi-location array
            "locations": locs,
            "images": imgs,
            "what_we_did": self.what_we_did,
            "notes": self.notes,
            "rating": self.rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DateImage(Base):
    __tablename__ = "date_images"

    id = Column(Integer, primary_key=True, index=True)
    date_id = Column(Integer, ForeignKey("dates.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    caption = Column(String(300), nullable=True)
    uploaded_at = Column(DateTime, default=func.now())

    date = relationship("DateEntry", back_populates="images")


class DateLocation(Base):
    """One row per location stop on a date — a date can have many."""
    __tablename__ = "date_locations"

    id         = Column(Integer, primary_key=True, index=True)
    date_id    = Column(Integer, ForeignKey("dates.id"), nullable=False)
    name       = Column(String(300), nullable=False)
    lat        = Column(Float, nullable=True)
    lon        = Column(Float, nullable=True)
    label      = Column(String(120), nullable=True)   # e.g. "Stop 1 — Dinner"
    sort_order = Column(Integer, default=0)

    date = relationship("DateEntry", back_populates="locations")


class CommEntry(Base):
    __tablename__ = "comms"

    id = Column(Integer, primary_key=True, index=True)
    comm_datetime = Column(DateTime, nullable=False)
    comm_type = Column(String(80), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "comm_datetime": self.comm_datetime.isoformat() if self.comm_datetime else None,
            "comm_type": self.comm_type,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AppSettings(Base):
    """Simple key-value store for app-level settings (partner names, etc.)."""
    __tablename__ = "app_settings"

    key   = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)


class BucketListItem(Base):
    """A shared date-idea wish list item the couple can check off."""
    __tablename__ = "bucket_list"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(300), nullable=False)
    notes       = Column(Text, nullable=True)
    done        = Column(Integer, default=0)            # 0 = todo, 1 = done
    date_id     = Column(Integer, ForeignKey("dates.id"), nullable=True)  # link to the date that fulfilled it
    created_at  = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)

    date = relationship("DateEntry")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "notes": self.notes,
            "done": bool(self.done),
            "date_id": self.date_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class User(Base):
    """One row per partner (partner1 / partner2).  Seeded from env vars on startup."""
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(50),  unique=True, nullable=False)   # "partner1" / "partner2"
    display_name    = Column(String(200), nullable=False, default="")
    hashed_password = Column(String(255), nullable=True)
    created_at      = Column(DateTime, default=func.now())

    passkeys = relationship("WebAuthnCredential", back_populates="user",
                            cascade="all, delete-orphan")


class WebAuthnCredential(Base):
    """Stores a registered Face ID / Touch ID / passkey for one user."""
    __tablename__ = "webauthn_credentials"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    credential_id = Column(Text, nullable=False, unique=True)   # base64url
    public_key    = Column(Text, nullable=False)                # base64 CBOR key
    sign_count    = Column(Integer, default=0)
    device_name   = Column(String(200), nullable=True)
    created_at    = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="passkeys")


class AuditLog(Base):
    """Records every create / update / delete across dates and comms."""
    __tablename__ = "audit_log"

    id           = Column(Integer, primary_key=True, index=True)
    timestamp    = Column(DateTime, default=func.now())
    changed_by   = Column(String(100), nullable=False)
    action       = Column(String(20),  nullable=False)   # created | updated | deleted
    entity_type  = Column(String(20),  nullable=False)   # date | comm
    entity_id    = Column(Integer,     nullable=False)
    entity_title = Column(String(300), nullable=True)    # snapshot of title at time of change
    changes_json = Column(Text,        nullable=True)    # JSON field diff

    @property
    def changes(self) -> dict:
        if self.changes_json:
            try:
                return _json.loads(self.changes_json)
            except Exception:
                return {}
        return {}
