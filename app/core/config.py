from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "dev"
    gemini_api_key: str
    AWS_REGION: str = "us-west-1"
    S3_BUCKET_NAME: str
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
