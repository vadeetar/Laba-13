"""Распространение trace-context через заголовки NATS (W3C Trace Context)."""

from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer(__name__)


def inject_trace_headers() -> dict[str, str]:
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


async def nats_request_with_trace(
    nc,
    subject: str,
    payload: bytes,
    timeout: float,
):
    headers = inject_trace_headers()
    with tracer.start_as_current_span(
        f"nats.request.{subject}",
        kind=SpanKind.CLIENT,
    ):
        return await nc.request(subject, payload, timeout=timeout, headers=headers)
