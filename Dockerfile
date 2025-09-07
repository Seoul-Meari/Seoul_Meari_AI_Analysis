FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 시스템 도구 (필요 시 추가)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 파일을 명시적으로 복사
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# 개발은 소스 마운트로 대체할 거라 COPY 생략 가능(운영 이미지에선 COPY app 추가)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
