from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo
from app.services import analysis_service
from app.db.session import SessionLocal
from datetime import datetime, timedelta

# 스케줄러 설정
scheduler = BackgroundScheduler(
    job_defaults={
        "coalesce": True,         # 밀린 트리거는 1번만 실행
        "max_instances": 1,       # 겹치기 방지
        "misfire_grace_time": 300 # 5분 지연까지 허용
    },
    timezone=ZoneInfo('Asia/Seoul'))

def batch_analyze_job():
    """3시간마다 실행되는 배치 분석 작업"""
    try:
        # DB 세션 생성
        with SessionLocal() as db:
            now = datetime.now(ZoneInfo('Asia/Seoul'))
            one_hour_ago = now - timedelta(hours=1)
            
            # 디렉터리 prefix (날짜만)
            date_prefix = now.strftime("upload_image/%Y%m%d")
            
            # 키 범위 설정 (UTC 보정: 9시간 감소)
            adj_one_hour_ago = one_hour_ago - timedelta(hours=9)
            adj_now = now - timedelta(hours=9)
            start_key = adj_one_hour_ago.strftime("%H%M%S")
            end_key = adj_now.strftime("%H%M%S")
            
            print(f"분석 범위: {date_prefix}/ ({start_key} ~ {end_key})")
            result = analysis_service.batch_analyze_images(limit=50, prefix=date_prefix, start_key=start_key, end_key=end_key, save_location=True, db=db)
            print(f"배치 분석 완료: {result.get('total_count', 0)}개 이미지 처리")
    except Exception as e:
        print(f"배치 분석 오류: {e}")

# 1시간마다 실행하는 작업 추가
def init_jobs():
    scheduler.add_job(
        batch_analyze_job,
        trigger=IntervalTrigger(hours=1, timezone=ZoneInfo('Asia/Seoul')), 
        id='batch_analyze_job',
        name='S3 이미지 배치 분석',
        replace_existing=True,
        next_run_time=datetime.now(ZoneInfo('Asia/Seoul'))
    )