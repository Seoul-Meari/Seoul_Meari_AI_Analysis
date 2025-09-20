from sqlalchemy import Column, Float, Integer, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.db.session import Base
from uuid import uuid4

class Complaint(Base):
    __tablename__ = "complaints"
    complaint_id = Column(UUID(as_uuid=True), primary_key=True)  # DB에 기본값 없으니 코드에서 채움
    latitude     = Column(Float)
    longitude    = Column(Float)
    accuracy     = Column(Integer)
    altitude     = Column(Float)
    coordinates  = Column(Float)
    direction    = Column(Float)
    timestamp    = Column(DateTime(timezone=True))
    image_url    = Column(Text)
    danger       = Column(Text)
    solution     = Column(Text)
    detail       = Column(Text)
    is_confirmed = Column(Boolean)

def insert_complaint(db, latitude, longitude, accuracy, altitude, coordinates, direction, timestamp, image_url, danger, solution, detail):
    row = Complaint(
        complaint_id=uuid4(),
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
        altitude=altitude,
        coordinates=coordinates,
        direction=direction,
        timestamp=timestamp,
        image_url=image_url,
        danger=danger,
        solution=solution,
        detail=detail,
        is_confirmed=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row