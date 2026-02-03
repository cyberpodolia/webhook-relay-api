from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger("app.relay")


async def relay_event(event: Dict[str, Any], target_url: str, request_id: str) -> Dict[str, Any]:
    delays = [0.2, 0.5, 1.0]
    last_status = None

    for attempt, delay in enumerate(delays, start=1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    target_url,
                    json=event,
                    headers={"X-Request-ID": request_id},
                )
            last_status = response.status_code
            if 200 <= response.status_code < 300:
                logger.info(
                    "relay_success",
                    extra={"status_code": response.status_code, "attempt": attempt},
                )
                return {"attempted": True, "success": True, "status_code": response.status_code}
            logger.warning(
                "relay_non_2xx",
                extra={"status_code": response.status_code, "attempt": attempt},
            )
        except Exception as exc:
            logger.warning("relay_error", extra={"attempt": attempt, "error": str(exc)})

        await asyncio.sleep(delay)

    return {"attempted": True, "success": False, "status_code": last_status}
