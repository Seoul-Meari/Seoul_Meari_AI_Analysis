# Seoul Meari AI Analysis

서울 메아리(Seoul Meari)의 **AI 도시 진단** 배치 분석 서버입니다. Unity 앱이 온디바이스 YOLO로 걸러 S3에 올린 거리 사진을 주기적으로 가져와 AWS Bedrock(Claude 3.5 Sonnet)으로 분석하고, 결과를 민원(`complaints`) 레코드로 PostgreSQL에 저장합니다. 저장된 민원은 관리자 콘솔의 "AI 도시 진단" 화면에 표시됩니다.

| 구분 | 내용 |
|---|---|
| 프레임워크 | FastAPI + Uvicorn (Python 3.12) |
| AI | AWS Bedrock `anthropic.claude-3-5-sonnet-20240620-v1:0` (Converse API) |
| 스토리지 | AWS S3 (boto3, IAM Role 자격 증명) |
| 데이터베이스 | PostgreSQL (SQLAlchemy, psycopg2) — 백엔드와 같은 DB의 `complaints` 테이블 |
| 스케줄러 | APScheduler `BackgroundScheduler` (Asia/Seoul) |
| 이미지 처리 | Pillow (EXIF/GPS 추출), XMP 파싱 |

## 서울 메아리 프로젝트

| 저장소 | 역할 |
|---|---|
| [Seoul_Meari_Client](https://github.com/Team-Little-Brother/Seoul_Meari_Client) | Unity 모바일 AR 앱 — AR 배경을 주기 캡처하고 YOLO(Sentis)로 쓰레기 검출 후 S3 업로드 |
| [Seoul_Meari_Backend](https://github.com/Team-Little-Brother/Seoul_Meari_Backend) | NestJS API — Presigned URL 발급, 민원 조회·해결, 대시보드 집계 |
| **Seoul_Meari_AI_Analysis** (현재) | 배치 분석 서버 — S3 이미지 → Bedrock 진단 → `complaints` 저장 |
| [Seoul_Meari_manage_Client](https://github.com/Team-Little-Brother/Seoul_Meari_manage_Client) | React 관리자 콘솔 — 진단 결과 확인·해결 처리 |

## 동작 흐름

```mermaid
sequenceDiagram
    participant U as Unity 앱
    participant B as NestJS Backend
    participant S3 as AWS S3
    participant A as AI Analysis (이 서버)
    participant BR as Bedrock Claude 3.5
    participant DB as PostgreSQL

    U->>U: AR 배경 10초 주기 캡처 + YOLO 검출 (sld/slp)
    U->>B: POST /api/s3/presigned-urls/analysis
    B-->>U: upload_image/{YYYYMMDD}/{HHmmss}_{tag}_{id}.jpg
    U->>S3: PUT (XMP에 GPS 포함)
    loop 매 1시간 (APScheduler)
        A->>S3: list_objects_v2(prefix=upload_image/{오늘}) + 최근 1시간 키 필터
        A->>S3: 이미지 다운로드 → EXIF/XMP GPS 추출
        A->>BR: converse(태그:URL 목록 + 프롬프트)
        BR-->>A: JSON 배열 [{image_url, detail, danger, solution}]
        A->>DB: INSERT complaints (좌표, 태그, S3 키, 진단 내용)
    end
```

1. **수집**: S3 키 규칙 `upload_image/{YYYYMMDD}/{HHmmss}_{tag}_{uuid8}.jpg`에서 시간과 태그를 파싱합니다. 스케줄러는 현재 시각 기준 최근 1시간 범위(`HHmmss` 비교, UTC 보정 -9h)만 조회하고 최대 50장을 처리합니다.
2. **메타데이터**: Pillow로 EXIF GPS(`GPSLatitude/Longitude/Altitude/ImgDirection`)를 십진수로 변환합니다. EXIF가 없으면 Unity 앱이 JPEG에 주입한 XMP(`exif:GPSLatitude/Longitude`)를 정규식으로 읽습니다.
3. **분석**: 태그(`sld` 페트병·캔 같은 단단한 쓰레기, `slp` 비닐·종이 같은 비정형 쓰레기)와 Presigned URL 목록을 하나의 프롬프트로 묶어 Bedrock Converse API에 보냅니다(`temperature 0.3`, `maxTokens 4000`). 응답은 JSON 배열만 오도록 지시하고, 코드펜스 제거 후 `[`~`]` 구간만 안전 파싱합니다.
4. **저장**: 응답의 `image_url`을 입력 URL과 매칭해 `detail / danger / solution`, GPS 좌표, S3 키, 태그를 `complaints`에 `is_confirmed = false`로 INSERT 합니다.

## API

모든 경로는 `/analysis` 아래에 있습니다. Swagger UI는 `http://localhost:8000/docs`에서 볼 수 있습니다.

| Method | Path | 설명 |
|---|---|---|
| GET | `/analysis/` | 서버 살아있음 확인 |
| GET | `/analysis/health/db` | `SELECT 1`로 DB 연결 확인 |
| GET | `/analysis/health/s3` | 버킷 `list_objects_v2` 1건으로 S3 접근 확인 |
| GET | `/analysis/health/bedrock` | `list_foundation_models`로 Bedrock 권한 확인 |
| GET | `/analysis/image-metadata?image_url=` | 이미지 URL의 EXIF·GPS·HTTP 헤더 메타데이터 |
| GET | `/analysis/s3-images?limit&prefix` | S3 이미지 목록(Presigned GET URL 포함) |
| POST | `/analysis/analyze-image?save_location=` | 단일 이미지 분석. body `{ "image_url": "..." }` |
| POST | `/analysis/batch-analyze?limit&prefix&save_location` | S3 prefix 기준 배치 분석 + DB 저장 (스케줄러와 동일 로직) |
| POST | `/analysis/analyze-and-save-db-test` | body `{ "image_urls": [...] }` 여러 URL 분석 + 저장 (테스트용) |

`batch-analyze` 응답 예시:

```json
{
  "success": true,
  "results": [
    {
      "tag": "sld",
      "image_url": "sld : https://bucket.s3.../upload_image/20250926/091240_sld_a1b2c3d4.jpg?...",
      "detail": "경복궁 인근 인도에 페트병과 캔이 방치되어 있습니다.",
      "danger": "보행자 통행 방해 및 미관 저해",
      "solution": "해당 구역 순찰 배정 및 수거 요청",
      "gps_data": { "latitude_decimal": 37.5796, "longitude_decimal": 126.977, "altitude": 41.0 },
      "s3_key": "upload_image/20250926/091240_sld_a1b2c3d4.jpg",
      "s3_info": { "key": "...", "last_modified": "...", "size": 123456 }
    }
  ],
  "total_count": 1,
  "detected_count": 1,
  "saved_complaints": 1
}
```

## 프로젝트 구조

```
app/
├── main.py                       # FastAPI 앱, startup/shutdown에서 스케줄러 기동·종료
├── core/config.py                # pydantic-settings (.env)
├── api/v1/
│   ├── routers.py                # /analysis 라우터 등록
│   └── analysis/analysis.py      # 헬스체크·메타데이터·분석 엔드포인트
├── services/analysis_service.py  # S3 목록, EXIF/XMP GPS 추출, Bedrock 호출, 결과 매칭·저장
├── infra/scheduler.py            # APScheduler 배치 잡 (1시간 간격, 즉시 1회 실행)
├── models/complaints.py          # SQLAlchemy Complaint 모델 + insert_complaint
├── schemas/analysis.py           # 요청/응답 Pydantic 스키마
└── db/session.py                 # 엔진·세션, DATABASE_URL 또는 개별 항목으로 URL 조립
```

## 실행 방법

### 환경 변수 (`.env`)

```env
APP_ENV=dev

# AWS (자격 증명은 IAM Role 또는 ~/.aws 사용)
AWS_REGION=us-west-1            # S3 리전
AWS_BEDROCK_REGION=us-east-1    # Bedrock 리전 (Claude 3.5 Sonnet 제공 리전)
S3_BUCKET_NAME=your-bucket

# PostgreSQL — DATABASE_URL이 있으면 우선, 없으면 아래 항목으로 조립
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/seoul_meari
DB_HOST=localhost
DB_PORT=5432
DB_NAME=seoul_meari
DB_USER=postgres
DB_PASSWORD=postgres
```

`complaints` 테이블은 백엔드(NestJS TypeORM)가 생성·관리하는 테이블을 그대로 사용하므로 두 서비스가 같은 DB를 바라봐야 합니다.

### Docker (권장)

```bash
docker compose up --build
# http://localhost:8000/docs
```

`docker-compose.yml`은 `./app`을 마운트하고 `--reload`로 실행하며, 호스트의 `~/.aws`를 읽기 전용으로 마운트해 자격 증명을 공유합니다.

### 로컬

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

서버가 뜨면 스케줄러가 즉시 1회 배치를 실행하고 이후 1시간마다 반복합니다(`coalesce`, `max_instances=1`, `misfire_grace_time=300s`). 배치를 끄고 API만 쓰려면 `app/main.py`의 `startup_event`에서 `scheduler.start()`를 주석 처리하세요.

## 참고 사항

- 이미지 URL 입력은 `"{tag} : {url}"` 형식을 허용하며, 태그가 없으면 원본 문자열 전체를 URL로 취급합니다.
- Bedrock 응답에서 URL이 매칭되지 않은 항목은 저장하지 않습니다. 매칭 실패 시 서버 로그에 `no match in image_data_list` 가 남습니다.
- GPS가 없는 이미지도 좌표 `NULL`로 저장됩니다. `timestamp`는 현재 저장하지 않습니다.
- Bedrock 호출은 `read_timeout 360s`, 재시도 3회로 설정되어 있습니다. 배치 50장 기준 응답까지 수 분이 걸릴 수 있습니다.
