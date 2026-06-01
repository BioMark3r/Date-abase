from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, func
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
    rating = Column(Integer, default=5)  # 1-5 hearts
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "pre_date_activities": self.pre_date_activities,
            "date_datetime": self.date_datetime.isoformat() if self.date_datetime else None,
            "duration_minutes": self.duration_minutes,
            "location_name": self.location_name,
            "location_lat": self.location_lat,
            "location_lon": self.location_lon,
            "what_we_did": self.what_we_did,
            "notes": self.notes,
            "rating": self.rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
