"""Security helpers for webhook verification, size limits, and admin auth."""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import HTTPException


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, secret: str) -> None:
    """Verify HMAC-SHA256 over the raw request body.

    Raises:
        HTTPException: 401 if verification is enabled and the signature is missing/invalid.
    """
    if not secret:
        # Rationale: signature verification is optional for local/dev usage.
        return
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    # Security: constant-time comparison avoids timing side channels.
    if not hmac.compare_digest(expected, signature_header.strip()):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def enforce_body_size_limit(raw_body: bytes, max_body_bytes: int) -> None:
    """Reject payloads larger than the configured byte limit."""
    if len(raw_body) > max_body_bytes:
        raise HTTPException(status_code=413, detail="Request body too large")


def require_admin_token(header_token: Optional[str], expected_token: str) -> None:
    """Validate admin token for privileged endpoints.

    Raises:
        HTTPException: 403 when admin access is disabled; 401 on invalid token.
    """
    if not expected_token:
        raise HTTPException(status_code=403, detail="Admin endpoint disabled")
    if not header_token or not hmac.compare_digest(header_token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid admin token")
