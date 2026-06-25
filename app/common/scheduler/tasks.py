"""스케줄러 예제 작업 모듈.

새로운 작업을 추가하려면 app/ 아래 아무 패키지에 tasks.py 파일을 만들고
@scheduled_task 데코레이터를 사용하면 된다. 서버 시작 시 자동으로 발견된다.

예:
    app/oss/mtc/tasks.py
    app/common/ftp_proxy/tasks.py
"""

# import logging
#
# from app.common.scheduler import scheduled_task
#
# logger = logging.getLogger(__name__)
#
#
# # --- interval 방식: 일정 간격으로 반복 ---
#
# @scheduled_task("interval", minutes=30, job_id="example-interval")
# async def example_interval_task():
#     """30분마다 실행되는 작업 예제."""
#     logger.info("interval task 실행")
#
#
# # --- cron 방식: 특정 시각에 실행 ---
#
# @scheduled_task("cron", hour=3, minute=0, job_id="example-cron")
# async def example_cron_task():
#     """매일 03:00에 실행되는 작업 예제."""
#     logger.info("cron task 실행")
#
#
# # --- sync 함수도 가능 (APScheduler가 자동으로 스레드풀에서 실행) ---
#
# @scheduled_task("interval", hours=1, job_id="example-sync")
# def example_sync_task():
#     """블로킹 I/O가 필요한 경우 sync 함수로 작성하면 된다."""
#     logger.info("sync task 실행 (thread pool)")
