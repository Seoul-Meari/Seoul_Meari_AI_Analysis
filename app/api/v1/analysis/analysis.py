from fastapi import APIRouter, Query
from app.services import analysis_service
from app.schemas.analysis import ImageAnalysisRequest, ImageMetadataResponse

router = APIRouter()


@router.get("/")
def root():
    return {"ok": True}

@router.get("/image-metadata", response_model=ImageMetadataResponse)
def get_image_metadata(image_url: str):
    result = analysis_service.get_image_metadata_from_url(image_url)
    if result["success"] and "gps" in result["metadata"]:
        from app.schemas.analysis import GPSData
        
        # GPS 데이터 필드명 매핑 및 타입 변환
        gps_raw = result["metadata"]["gps"]
        
        def parse_fraction(value):
            """분수 문자열을 float로 변환합니다."""
            if value is None:
                return None
            if isinstance(value, str) and '/' in value:
                numerator, denominator = value.split('/')
                return float(numerator) / float(denominator)
            return float(value) if value is not None else None
        
        def format_timestamp(value):
            """타임스탬프를 문자열로 변환합니다."""
            if value is None:
                return None
            if isinstance(value, (list, tuple)):
                return f"{value[0]}:{value[1]}:{value[2]}"
            return str(value)
        
        gps_mapped = {
            "latitude_decimal": gps_raw.get("latitude_decimal"),
            "longitude_decimal": gps_raw.get("longitude_decimal"),
            "coordinates": gps_raw.get("coordinates"),
            "altitude": parse_fraction(gps_raw.get("GPSAltitude")),
            "speed": parse_fraction(gps_raw.get("GPSSpeed")),
            "direction": parse_fraction(gps_raw.get("GPSImgDirection")),
            "timestamp": format_timestamp(gps_raw.get("GPSTimeStamp"))
        }
        
        gps_data = GPSData(**gps_mapped)
        return ImageMetadataResponse(
            success=True,
            metadata=result["metadata"],
            gps_data=gps_data
        )
    return result

@router.post("/analyze-image")
def analyze_image(request: ImageAnalysisRequest, save_location: bool = Query(True, description="위치 데이터 저장 여부")):
    return analysis_service.analyze_image(request.image_url, save_location)