"""Динамическое масштабирование: мониторинг очереди в Redis + Docker Compose scale."""

import logging
import os
import subprocess
from pathlib import Path

import redis

from app.config import settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "mas:pipeline_queue_depth"
AUTOSCALE_LOG_KEY = "mas:autoscale_events"

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def queue_push() -> int:
    r = get_redis()
    depth = r.incr(QUEUE_KEY)
    logger.info("Queue depth increased: %d", depth)
    return int(depth)


def queue_pop() -> int:
    r = get_redis()
    depth = r.decr(QUEUE_KEY)
    if depth < 0:
        r.set(QUEUE_KEY, 0)
        depth = 0
    logger.info("Queue depth decreased: %d", depth)
    return int(depth)


def queue_depth() -> int:
    val = get_redis().get(QUEUE_KEY)
    return int(val or 0)


def log_autoscale_event(message: str) -> None:
    r = get_redis()
    r.lpush(AUTOSCALE_LOG_KEY, message)
    r.ltrim(AUTOSCALE_LOG_KEY, 0, 49)


def get_autoscale_events(limit: int = 10) -> list[str]:
    return get_redis().lrange(AUTOSCALE_LOG_KEY, 0, limit - 1)


def try_scale_appointment_agents(depth: int) -> bool:
    """
    При превышении порога масштабируем appointment-agent через Docker Compose.
    Требует mount docker.sock и compose-файла в orchestrator.
    """
    if depth <= settings.queue_scale_threshold:
        return False

    if not settings.autoscale_enabled:
        logger.warning("Autoscale skipped (AUTOSCALE_ENABLED=false)")
        return False

    compose_file = Path(settings.compose_file)
    if not compose_file.is_file():
        logger.error("Compose file not found: %s", compose_file)
        return False

    target_replicas = min(settings.autoscale_max_replicas, 2 + (depth // settings.queue_scale_threshold))

    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "up",
        "-d",
        "--no-recreate",
        "--scale",
        f"{settings.autoscale_service}={target_replicas}",
    ]

    logger.warning("Autoscaling: depth=%d -> %s", depth, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=str(compose_file.parent),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "COMPOSE_PROJECT_NAME": settings.compose_project_name},
        )
        if result.returncode == 0:
            msg = f"Scaled {settings.autoscale_service} to {target_replicas} (queue={depth})"
            log_autoscale_event(msg)
            logger.info(msg)
            return True
        logger.error("Autoscale failed: %s", result.stderr)
        log_autoscale_event(f"FAILED scale to {target_replicas}: {result.stderr[:200]}")
    except Exception as exc:
        logger.error("Autoscale error: %s", exc)
        log_autoscale_event(f"ERROR: {exc}")
    return False
