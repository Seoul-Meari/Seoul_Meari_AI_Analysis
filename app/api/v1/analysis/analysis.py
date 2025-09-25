from fastapi import APIRouter, Query
from app.services import analysis_service
from app.schemas.analysis import ImageAnalysisRequest, ImageMetadataResponse, BatchImageAnalysisRequest
from sqlalchemy.orm import Session
from app.db.session import get_db
from fastapi import Depends
from sqlalchemy import text
from app.core.config import settings

router = APIRouter()


@router.get("/")
def root():
    return {"ok": True}

@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "db": "connected"}
    except Exception as e:
        return {"ok": False, "db": "error", "error": str(e)}

@router.get("/health/s3")
def health_s3():
    try:
        from app.services.analysis_service import s3_client
        # 지정된 버킷에서 객체 1개 조회 시도
        bucket = settings.S3_BUCKET_NAME
        resp = s3_client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        count = resp.get("KeyCount", 0)
        return {"ok": True, "s3": "connected", "bucket": bucket, "keyCount": count}
    except Exception as e:
        return {"ok": False, "s3": "error", "error": str(e)}

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
def analyze_image(request: ImageAnalysisRequest, save_location: bool = Query(True, description="위치 데이터 저장 여부"), db: Session = Depends(get_db)):
    return analysis_service.analyze_image([request.image_url], save_location, db)

@router.get("/s3-images")
def get_s3_images(limit: int = Query(50, description="가져올 이미지 개수"), prefix: str = Query("", description="S3 키 prefix 필터")):
    """S3에서 이미지 목록을 가져옵니다."""
    return analysis_service.get_s3_image_urls(limit, prefix)

@router.post("/batch-analyze")
def batch_analyze(
    limit: int = Query(50, description="분석할 이미지 개수"), 
    prefix: str = Query("", description="S3 키 prefix 필터"),
    save_location: bool = Query(True, description="위치 데이터 저장 여부"),
    db: Session = Depends(get_db)
):
    """S3에서 이미지들을 배치로 분석합니다."""
    return analysis_service.batch_analyze_images(limit, prefix, save_location, db)

@router.post("/analyze-and-save-db-test")
def analyze_and_save_db_test(
    request: BatchImageAnalysisRequest,
    db: Session = Depends(get_db)
):
    return analysis_service.analyze_and_save_db_test(request.image_urls, db)
