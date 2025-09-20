from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "dev"
    AWS_REGION: str = "ap-northeast-2"
    AWS_BEDROCK_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str
    # AWS 설정
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
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
