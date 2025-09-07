from pydantic import BaseModel

class ImageAnalysisRequest(BaseModel):
    image_url: str