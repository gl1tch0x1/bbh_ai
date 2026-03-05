from celery import Celery
import os

# Celery app initialization with local Redis
celery = Celery(
    "bbh_ai",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)

# Production-grade configuration
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,       # Prevent task hoarding (crucial for long-running security tools)
    task_acks_late=True,                # Ensure task is re-queued if worker fails
    task_reject_on_worker_lost=True,    # Reject task if worker process is lost
    worker_max_tasks_per_child=50,      # Prevent memory leaks from long-running tool wrappers
    task_time_limit=1800,               # 30-minute hard limit per task
    task_soft_time_limit=1500,          # 25-minute soft limit
    worker_send_task_events=True,       # Enable monitoring
    task_track_started=True,
    timezone='UTC',
    enable_utc=True,
)

# Define separate queues for better resource management
# Note: exploit_tasks module does not exist; vulnerability scanning uses vuln_tasks
celery.conf.task_routes = {
    'tasks.recon_tasks.*':  {'queue': 'recon'},
    'tasks.vuln_tasks.*':   {'queue': 'vuln'},
    'tasks.report_tasks.*': {'queue': 'reporting'},
    'tasks.phase_tasks.*':  {'queue': 'phases'},
}
