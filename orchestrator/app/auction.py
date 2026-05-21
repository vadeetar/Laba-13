"""Аукционное распределение: агенты публикуют ставки (cost, skill) через NATS."""

import asyncio
import json
import logging
from typing import Optional

import nats

from app.tracing_util import inject_trace_headers, tracer

logger = logging.getLogger(__name__)


async def collect_auction_bids(
    nc: nats.NATS,
    task_id: str,
    timeout_sec: float = 2.0,
) -> tuple[dict, list[dict]]:
    """
    Публикуем tasks.auction с inbox; все appointment-агенты отвечают ставкой.
    Победитель — минимальный cost, при равенстве — больший skill.
    """
    inbox = nc.new_inbox()
    sub = await nc.subscribe(inbox, max_msgs=20)

    payload = json.dumps({"task_id": task_id}, ensure_ascii=False).encode()
    headers = inject_trace_headers()

    with tracer.start_as_current_span("auction.collect_bids"):
        await nc.publish("tasks.auction", payload, reply=inbox, headers=headers)

        bids: list[dict] = []
        deadline = asyncio.get_running_loop().time() + timeout_sec

        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                msg = await sub.next_msg(timeout=min(remaining, 0.4))
                bid = json.loads(msg.data.decode())
                if bid.get("available", True):
                    bids.append(bid)
                    logger.info(
                        "Auction bid: agent=%s cost=%s skill=%s",
                        bid.get("agent_id"),
                        bid.get("cost"),
                        bid.get("skill"),
                    )
            except nats.errors.TimeoutError:
                continue

        await sub.unsubscribe()

    if not bids:
        raise RuntimeError("Ни один агент не ответил на аукцион (tasks.auction)")

    winner = min(bids, key=lambda b: (b.get("cost", 999), -float(b.get("skill", 0))))
    logger.info(
        "Auction winner: %s (cost=%s, skill=%s) from %d bids",
        winner.get("agent_id"),
        winner.get("cost"),
        winner.get("skill"),
        len(bids),
    )
    return winner, bids
