from fastapi import APIRouter
from app.services import analysis_service
from app.schemas.analysis import ImageAnalysisRequest

router = APIRouter()


@router.get("/")
def root():
    return {"ok": True}

@router.post("/llm")
def llm(ask: str):
    return analysis_service.llm(ask)

@router.post("/analyze-image")
def analyze_image(request: ImageAnalysisRequest):
    return analysis_service.analyze_image(request.image_url)