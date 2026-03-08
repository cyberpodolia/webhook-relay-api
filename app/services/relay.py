"""Outbound relay execution with SSRF checks, retries, and metrics.

The API layer calls this module to relay stored events to `TARGET_URL`. This
module performs target preflight validation, uses a shared async HTTP client, and
returns structured outcomes instead of raising for expected relay failures.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from app.metrics import RELAY_ATTEMPTS_TOTAL, RELAY_LATENCY_SECONDS, RELAY_SUCCESSES_TOTAL

logger = logging.getLogger("app.relay")

_BLOCKED_IP_FLAGS = (
    "is_private",
    "is_loopback",
    "is_link_local",
    "is_reserved",
    "is_multicast",
    "is_unspecified",
)

_client: httpx.AsyncClient | None = None
_dispatch_queue: asyncio.Queue[Callable[[], Awaitable[None]]] | None = None
_dispatch_workers: list[asyncio.Task[None]] = []


@dataclass
class RelayOutcome:
    """Internal relay result before conversion to JSON-serializable dict output."""

    attempted: bool
    success: bool
    reason: str | None = None
    status_code: int | None = None
    attempts: int = 0
    last_error: str | None = None
    last_attempt_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the dataclass to the response/persistence payload shape."""
        return {
            "attempted": self.attempted,
            "success": self.success,
            "reason": self.reason,
            "status_code": self.status_code,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "last_attempt_at": self.last_attempt_at,
        }


async def startup_http_client() -> None:
    """Create the process-wide AsyncClient at application startup."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=5.0)


async def shutdown_http_client() -> None:
    """Close the shared AsyncClient at application shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _relay_dispatch_worker(worker_index: int) -> None:
    """Execute queued relay jobs in a bounded worker pool."""
    queue = _dispatch_queue
    if queue is None:
        return
    while True:
        job = await queue.get()
        try:
            await job()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("relay_dispatch_job_failed", extra={"worker": worker_index})
        finally:
            queue.task_done()


async def startup_relay_dispatcher(worker_count: int, queue_size: int) -> None:
    """Initialize bounded relay dispatch queue and worker tasks."""
    global _dispatch_queue, _dispatch_workers
    if _dispatch_queue is not None:
        return
    _dispatch_queue = asyncio.Queue(maxsize=max(queue_size, 1))
    _dispatch_workers = [
        asyncio.create_task(_relay_dispatch_worker(idx)) for idx in range(max(worker_count, 1))
    ]


async def shutdown_relay_dispatcher() -> None:
    """Stop relay dispatch workers during app shutdown."""
    global _dispatch_queue, _dispatch_workers
    workers = list(_dispatch_workers)
    _dispatch_workers = []
    _dispatch_queue = None
    for worker in workers:
        worker.cancel()
    if workers:
        await asyncio.gather(*workers, return_exceptions=True)


def enqueue_relay_job(job: Callable[[], Awaitable[None]]) -> bool:
    """Schedule relay work without blocking the intake request path."""
    if _dispatch_queue is None:
        raise RuntimeError("Relay dispatcher is not initialized")
    try:
        _dispatch_queue.put_nowait(job)
        return True
    except asyncio.QueueFull:
        return False


def relay_queue_has_capacity() -> bool:
    """Return True when the dispatcher queue can accept another relay job."""
    if _dispatch_queue is None:
        raise RuntimeError("Relay dispatcher is not initialized")
    return _dispatch_queue.qsize() < _dispatch_queue.maxsize


def _get_client() -> httpx.AsyncClient:
    """Return the initialized shared client or fail fast."""
    if _client is None:
        raise RuntimeError("Relay HTTP client not initialized")
    return _client


def _is_blocked_ip(ip_text: str) -> bool:
    """Return True when an IP falls into blocked local/private/reserved ranges."""
    ip_obj = ipaddress.ip_address(ip_text)
    return any(getattr(ip_obj, attr) for attr in _BLOCKED_IP_FLAGS)


async def _resolve_ips_for_host(host: str) -> set[str]:
    """Resolve a hostname to candidate IPs for SSRF screening.

    If `host` is already a literal IP, it is returned as-is.
    """
    try:
        ipaddress.ip_address(host)
        return {host}
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    ips = set()
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            ips.add(sockaddr[0])
    return ips


async def _preflight_target(
    target_url: str,
    relay_allow_hosts: set[str] | frozenset[str],
    relay_allow_private_ips: bool,
) -> RelayOutcome | None:
    """Validate scheme/host/IP policy before sending any outbound request.

    Returns:
        RelayOutcome | None: a skipped outcome if relay should not run, else None.
    """
    parsed = urlparse(target_url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    if scheme not in {"http", "https"}:
        return RelayOutcome(attempted=False, success=False, reason="unsupported_scheme")
    if not host:
        return RelayOutcome(attempted=False, success=False, reason="invalid_target_url")
    if relay_allow_hosts and host not in relay_allow_hosts:
        # Security: explicit hostname allowlist is checked before any request.
        return RelayOutcome(attempted=False, success=False, reason="host_not_allowed")

    try:
        for ip in await _resolve_ips_for_host(host):
            if not relay_allow_private_ips and _is_blocked_ip(ip):
                # Security: deny if any resolved record is unsafe (mixed answers).
                return RelayOutcome(attempted=False, success=False, reason="blocked_ip")
    except socket.gaierror as exc:
        return RelayOutcome(attempted=False, success=False, reason="dns_error", last_error=str(exc))

    return None


async def relay_event(
    event: dict[str, Any],
    target_url: str,
    request_id: str,
    relay_allow_hosts: set[str] | frozenset[str],
    relay_allow_private_ips: bool = False,
) -> dict[str, Any]:
    """Relay an event with jittered exponential backoff.

    Async expectations:
        Requires the shared HTTP client to be initialized by application startup.

    Error behavior:
        Expected network/HTTP failures are returned as structured payloads rather
        than raised, so the webhook intake path can still succeed.
    """
    preflight_result = await _preflight_target(
        target_url,
        relay_allow_hosts,
        relay_allow_private_ips,
    )
    if preflight_result is not None:
        return preflight_result.to_dict()

    client = _get_client()
    base_delay = 0.2
    factor = 2.0
    max_attempts = 4
    last_status: int | None = None
    last_error: str | None = None
    reason = "non_2xx"
    last_attempt_at: datetime | None = None

    for attempt in range(1, max_attempts + 1):
        RELAY_ATTEMPTS_TOTAL.inc()
        started = time.perf_counter()
        last_attempt_at = datetime.now(timezone.utc)
        try:
            response = await client.post(
                target_url,
                json=event,
                headers={"X-Request-ID": request_id},
            )
            RELAY_LATENCY_SECONDS.observe(time.perf_counter() - started)
            last_status = response.status_code
            if 200 <= response.status_code < 300:
                RELAY_SUCCESSES_TOTAL.inc()
                logger.info(
                    "relay_success",
                    extra={"status_code": response.status_code, "attempt": attempt},
                )
                return RelayOutcome(
                    attempted=True,
                    success=True,
                    reason="success",
                    status_code=response.status_code,
                    attempts=attempt,
                    last_attempt_at=last_attempt_at,
                ).to_dict()
            reason = "non_2xx"
            last_error = f"non-2xx response: {response.status_code}"
            logger.warning(
                "relay_non_2xx",
                extra={"status_code": response.status_code, "attempt": attempt},
            )
        except httpx.TimeoutException as exc:
            RELAY_LATENCY_SECONDS.observe(time.perf_counter() - started)
            reason = "timeout"
            last_error = str(exc) or "timeout"
            logger.warning("relay_timeout", extra={"attempt": attempt})
        except httpx.ConnectError as exc:
            RELAY_LATENCY_SECONDS.observe(time.perf_counter() - started)
            reason = "connection_error"
            last_error = str(exc) or "connection error"
            logger.warning("relay_connect_error", extra={"attempt": attempt, "error": str(exc)})
        except httpx.HTTPError as exc:
            RELAY_LATENCY_SECONDS.observe(time.perf_counter() - started)
            reason = "http_error"
            last_error = str(exc)
            logger.warning("relay_http_error", extra={"attempt": attempt, "error": str(exc)})

        if attempt < max_attempts:
            # Rationale: jitter reduces synchronized retry bursts during upstream incidents.
            delay = min(base_delay * (factor ** (attempt - 1)), 1.6)
            delay *= 1 + random.uniform(-0.2, 0.2)
            await asyncio.sleep(max(delay, 0.01))

    return RelayOutcome(
        attempted=True,
        success=False,
        reason=reason,
        status_code=last_status,
        attempts=max_attempts,
        last_error=last_error,
        last_attempt_at=last_attempt_at,
    ).to_dict()
