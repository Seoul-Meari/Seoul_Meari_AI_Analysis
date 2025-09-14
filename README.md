# Seoul_Meari_AI_Analysis

## 환경 설정

### .env 파일 생성
프로젝트 루트에 `.env` 파일을 생성하고 다음 설정을 추가하세요:

```env
# 애플리케이션 환경
APP_ENV=dev

# Gemini API
gemini_api_key=your_gemini_api_key_here

# AWS S3 설정
AWS_REGION=us-west-1
S3_BUCKET=your-s3-bucket-name
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key

# S3 추가 설정 (선택사항)
S3_ENDPOINT_URL=  # MinIO나 다른 S3 호환 서비스 사용 시
S3_USE_SSL=true
S3_SIGNATURE_VERSION=s3v4
S3_MAX_CONNECTIONS=10
S3_TIMEOUT=60
```

### S3 서비스 사용법

```python
from app.services.s3_service import s3_service

# 파일 업로드
success = s3_service.upload_file("local_file.jpg", "images/uploaded_file.jpg", "image/jpeg")

# 파일 다운로드
success = s3_service.download_file("images/uploaded_file.jpg", "downloaded_file.jpg")

# 사전 서명된 URL 생성 (임시 접근 링크)
url = s3_service.generate_presigned_url("images/uploaded_file.jpg", expiration=3600)

# 파일 존재 확인
exists = s3_service.file_exists("images/uploaded_file.jpg")

# 파일 삭제
success = s3_service.delete_file("images/uploaded_file.jpg")
```