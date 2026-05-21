"""Распространение trace-context через заголовки NATS (W3C Trace Context)."""

from typing import Optional

import nats
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer(__name__)


def headers_from_msg(msg: nats.Msg) -> dict[str, str]:
    if not msg.headers:
        return {}
    return {k: v[0] if isinstance(v, list) else str(v) for k, v in msg.headers.items()}


def inject_trace_headers() -> dict[str, str]:
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


def extract_context(headers: Optional[dict[str, str]]):
    if not headers:
        return trace.get_current_span().get_span_context()
    return extract(headers)


async def nats_request_with_trace(
    nc: nats.NATS,
    subject: str,
    payload: bytes,
    timeout: float,
) -> nats.Msg:
    headers = inject_trace_headers()
    with tracer.start_as_current_span(
        f"nats.request.{subject}",
        kind=SpanKind.CLIENT,
    ):
        return await nc.request(subject, payload, timeout=timeout, headers=headers)
