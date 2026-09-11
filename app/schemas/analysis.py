from pydantic import BaseModel
from typing import Optional, Dict, Any

class ImageAnalysisRequest(BaseModel):
    image_url: str

class BatchImageAnalysisRequest(BaseModel):
    image_urls: list[str]

class GPSData(BaseModel):
    latitude_decimal: Optional[float] = None
    longitude_decimal: Optional[float] = None
    coordinates: Optional[str] = None
    altitude: Optional[float] = None
    speed: Optional[float] = None
    direction: Optional[float] = None
    timestamp: Optional[str] = None

class ImageMetadataResponse(BaseModel):
    success: bool
    metadata: Optional[Dict[str, Any]] = None
    gps_data: Optional[GPSData] = None
    error: Optional[str] = None