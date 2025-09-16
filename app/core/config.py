from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "dev"
    gemini_api_key: str
    AWS_REGION: str = "us-west-1"
    AWS_BEDROCK_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str
    
    # 데이터베이스 설정
    DATABASE_URL: str
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
