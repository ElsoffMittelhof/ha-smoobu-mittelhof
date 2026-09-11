"""Async Smoobu API client using the 2026 HMAC authentication scheme."""
from __future__ import annotations

import base64
from datetime import date, datetime, timezone
import hashlib
import hmac
import json
from typing import Any, Mapping
from urllib.parse import quote
from uuid import uuid4

from aiohttp import ClientResponseError, ClientSession

BASE_URL = "https://login.smoobu.com"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class SmoobuApiError(Exception):
    """Base Smoobu API exception."""


class SmoobuAuthError(SmoobuApiError):
    """Authentication failed."""


class SmoobuApiClient:
    """Small async client for the Smoobu endpoints used by this integration."""

    def __init__(self, session: ClientSession, api_key: str, api_secret: str) -> None:
        self._session = session
        self._api_key = api_key.strip()
        self._api_secret = api_secret.strip()

    @staticmethod
    def _canonical_query(params: Mapping[str, Any] | None) -> str:
        if not params:
            return ""
        pairs: list[str] = []
        for key in sorted(params):
            value = params[key]
            if value is None:
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            pairs.append(f"{quote(str(key), safe='')}={quote(str(value), safe='')}")
        return "&".join(pairs)

    def _auth_headers(
        self,
        method: str,
        path: str,
        canonical_query: str,
        body: bytes,
    ) -> dict[str, str]:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        nonce = str(uuid4())
        body_hash = hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256
        canonical = "\n".join(
            [method.upper(), path, canonical_query, timestamp, nonce, body_hash, self._api_key]
        )
        signature = base64.b64encode(
            hmac.new(
                self._api_secret.encode("utf-8"),
                canonical.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("ascii")
        return {
            "X-API-Key": self._api_key,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature,
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        canonical_query = self._canonical_query(params)
        body = b""
        headers: dict[str, str]
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = self._auth_headers(method, path, canonical_query, body)
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        url = f"{BASE_URL}{path}"
        if canonical_query:
            url = f"{url}?{canonical_query}"

        try:
            async with self._session.request(
                method.upper(), url, headers=headers, data=body if json_body is not None else None
            ) as response:
                if response.status in (401, 403):
                    text = await response.text()
                    raise SmoobuAuthError(f"Smoobu authentication failed ({response.status}): {text[:300]}")
                response.raise_for_status()
                return await response.json(content_type=None)
        except SmoobuAuthError:
            raise
        except ClientResponseError as err:
            raise SmoobuApiError(f"Smoobu HTTP error: {err.status} {err.message}") from err
        except Exception as err:
            raise SmoobuApiError(f"Smoobu request failed: {err}") from err

    async def get_reservations(
        self,
        start: date | str,
        end: date | str,
        *,
        exclude_blocked: bool = True,
        apartment_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return all pages of reservations for a date range."""
        start_s = start.isoformat() if isinstance(start, date) else str(start)
        end_s = end.isoformat() if isinstance(end, date) else str(end)
        page = 1
        bookings: list[dict[str, Any]] = []
        while True:
            params: dict[str, Any] = {
                "excludeBlocked": exclude_blocked,
                "from": start_s,
                "page": page,
                "pageSize": 100,
                "to": end_s,
            }
            if apartment_id is not None:
                params["apartmentId"] = apartment_id
            payload = await self._request("GET", "/api/reservations", params=params)
            if not isinstance(payload, dict):
                raise SmoobuApiError("Unexpected reservations response format")
            page_bookings = payload.get("bookings", [])
            if isinstance(page_bookings, list):
                bookings.extend(item for item in page_bookings if isinstance(item, dict))
            page_count = int(payload.get("page_count") or payload.get("pageCount") or 1)
            if page >= page_count:
                break
            page += 1
        return bookings

    async def get_booking_placeholders(self, booking_id: int | str) -> dict[str, Any]:
        """Return booking placeholders as a key/value mapping.

        Smoobu documentation describes a {placeholders:[...]} response, while the
        user's live account has also returned the array directly. Both are accepted.
        """
        payload = await self._request("GET", f"/api/reservations/{booking_id}/placeholders")
        if isinstance(payload, dict):
            values = payload.get("placeholders", [])
        elif isinstance(payload, list):
            values = payload
        else:
            values = []
        result: dict[str, Any] = {}
        for item in values:
            if isinstance(item, dict) and item.get("key"):
                result[str(item["key"])] = item.get("value")
        return result

    async def get_custom_placeholders(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/custom-placeholders")
        if not isinstance(payload, dict):
            return []
        values = payload.get("customPlaceholders", [])
        return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []

    async def get_booking_custom_placeholders(self, booking_id: int | str) -> dict[str, Any]:
        values = await self.get_custom_placeholders()
        result: dict[str, Any] = {}
        for item in values:
            is_booking = str(item.get("type", "")) in {"1", "booking", "Booking"}
            if not is_booking or str(item.get("foreignId")) != str(booking_id):
                continue
            key = item.get("key")
            if key:
                result[str(key)] = item.get("defaultValue")
        return result
