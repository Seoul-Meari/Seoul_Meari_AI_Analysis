from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from app.core.config import settings
from urllib.parse import quote_plus

def _build_database_url() -> str:
    # DATABASE_URL이 유효한 형태(스킴 포함)이면 그대로 사용
    if getattr(settings, "DATABASE_URL", None):
        raw = settings.DATABASE_URL.strip()
        if "://" in raw:
            return raw
    # 없으면 개별 항목으로 조립
    user = settings.DB_USER
    password = quote_plus(settings.DB_PASSWORD)
    host = settings.DB_HOST
    port = settings.DB_PORT
    name = settings.DB_NAME
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

# 데이터베이스 엔진 생성 (pre_ping으로 연결 검증)
engine = create_engine(
    _build_database_url(),
    pool_pre_ping=True,
)

# 세션 팩토리 생성 (스레드 안전)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Base 클래스 생성
Base = declarative_base()

# 의존성 주입을 위한 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
