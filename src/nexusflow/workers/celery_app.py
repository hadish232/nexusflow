from celery import Celery
from kombu import Exchange, Queue

from nexusflow.config import settings


# ============================================================
# Celery application
# ============================================================

celery_app = Celery(
    "nexusflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "nexusflow.workers.tasks",
    ],
)


# ============================================================
# Durable task exchange
# ============================================================

default_exchange = Exchange(
    name="default",
    type="direct",
    durable=True,
)


# ============================================================
# Main task queue
#
# RabbitMQ quorum queue.
#
# This is the queue where actual jobs live.
# ============================================================

default_queue = Queue(
    name="default",
    exchange=default_exchange,
    routing_key="default",
    durable=True,
    queue_arguments={
        "x-queue-type": "quorum",
    },
)


# ============================================================
# Celery configuration
# ============================================================

celery_app.conf.update(
    # ----------------------------------------------------------
    # Serialization
    # ----------------------------------------------------------
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ----------------------------------------------------------
    # Time
    # ----------------------------------------------------------
    timezone="UTC",
    enable_utc=True,
    # ----------------------------------------------------------
    # Broker connection
    # ----------------------------------------------------------
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        # Required by RabbitMQ quorum queues.
        "confirm_publish": True,
    },
    # ----------------------------------------------------------
    # Default task queue
    # ----------------------------------------------------------
    task_default_queue="default",
    task_default_queue_type="quorum",
    task_default_exchange="default",
    task_default_exchange_type="direct",
    task_default_routing_key="default",
    # ----------------------------------------------------------
    # Explicit queue configuration
    # ----------------------------------------------------------
    task_queues=(default_queue,),
    # Unknown task queues should also use quorum queues.
    task_create_missing_queues=True,
    task_create_missing_queue_type="quorum",
    task_create_missing_queue_exchange_type="direct",
    # ----------------------------------------------------------
    # RabbitMQ quorum queue behavior
    # ----------------------------------------------------------
    worker_detect_quorum_queues=True,
    # ----------------------------------------------------------
    # Worker reliability
    # ----------------------------------------------------------
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # ----------------------------------------------------------
    # Worker events
    # ----------------------------------------------------------
    worker_send_task_events=True,
    task_track_started=True,
    # ----------------------------------------------------------
    # RabbitMQ control queues
    #
    # Durable + non-exclusive.
    # ----------------------------------------------------------
    control_queue_durable=True,
    control_queue_exclusive=False,
    # ----------------------------------------------------------
    # RabbitMQ event/gossip queues
    #
    # IMPORTANT:
    #
    # transient + exclusive is allowed.
    #
    # RabbitMQ 4.3 rejects transient + non-exclusive.
    # ----------------------------------------------------------
    event_queue_durable=False,
    event_queue_exclusive=True,
    # ----------------------------------------------------------
    # Event queue housekeeping
    # ----------------------------------------------------------
    event_queue_ttl=60,
    event_queue_expires=120,
    # ----------------------------------------------------------
    # Control queue housekeeping
    # ----------------------------------------------------------
    control_queue_ttl=300,
    control_queue_expires=10,
    # ----------------------------------------------------------
    # Beat schedule
    # ----------------------------------------------------------
    beat_schedule={
        "publish-outbox-events": {
            "task": ("nexusflow.workers.tasks.publish_outbox_events"),
            "schedule": settings.outbox_poll_seconds,
        },
    },
)
