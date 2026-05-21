"""Глобальное состояние для мониторинга (последние задачи, аукцион)."""

from collections import deque
from typing import Any, Optional

tasks_processed: int = 0
last_auction_winner: Optional[dict] = None
last_auction_bids: list[dict] = []
recent_results: deque[dict[str, Any]] = deque(maxlen=15)
last_run_result: str = ""
last_run_error: str = ""
