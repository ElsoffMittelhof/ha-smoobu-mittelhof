"""Offline Smoobu HMAC message API contract tests (no guest calls, no network)."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest

# The isolated CI does not install all Home Assistant runtime dependencies.
aiohttp_stub = ModuleType("aiohttp")
aiohttp_stub.ClientResponseError = type("ClientResponseError", (Exception,), {})
aiohttp_stub.ClientSession = type("ClientSession", (), {})
sys.modules.setdefault("aiohttp", aiohttp_stub)

path = Path(__file__).resolve().parents[1] / "custom_components" / "smoobu_mittelhof" / "api.py"
spec = importlib.util.spec_from_file_location("smoobu_api_test", path)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self, content_type=None):
        return self.payload


class StubSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, headers, data=None):
        self.calls.append((method, url, headers, data))
        if "/messages/send-message-to-guest" in url:
            return FakeResponse({"status": 201, "title": "Resource created successfully"})
        if "/messages" in url:
            if "page=2" in url:
                return FakeResponse({"messages": [{"id": 2, "type": 1}], "page_count": 2})
            return FakeResponse({"messages": [{"id": 1, "type": 2}], "page_count": 2})
        if "/threads" in url:
            return FakeResponse({"threads": [], "unread_messages": 0, "page_count": 1})
        return FakeResponse({
            "id": 1, "type": "reservation", "apartment": {"id": 2},
            "priceElements": [{"name": "Stay", "amount": 100}],
        })


class TestSmoobuGuestApi(unittest.TestCase):
    def test_read_booking_and_messages(self):
        async def go():
            session = StubSession()
            api = module.SmoobuApiClient(session, "api-key", "api-secret")
            booking = await api.get_booking(1)
            messages = await api.get_booking_messages(1)
            inbox = await api.get_message_threads()
            self.assertEqual(booking["priceElements"][0]["amount"], 100)
            self.assertEqual(len(messages), 2)
            self.assertEqual(inbox["threads"], [])
            self.assertTrue(any("includePriceElements=true" in call[1] for call in session.calls))
            self.assertTrue(any("onlyRelatedToGuest=true" in call[1] for call in session.calls))
            self.assertTrue(all(call[2].get("X-Signature") for call in session.calls))
            nonces = [call[2]["X-Nonce"] for call in session.calls]
            self.assertEqual(len(nonces), len(set(nonces)))
        asyncio.run(go())

    def test_post_does_not_happen_until_explicit_method_call(self):
        async def go():
            session = StubSession()
            api = module.SmoobuApiClient(session, "api-key", "api-secret")
            await api.get_booking(1)
            self.assertFalse(any(call[0] == "POST" for call in session.calls))
            await api.send_message_to_guest(1, "Subject", "Body")
            posts = [call for call in session.calls if call[0] == "POST"]
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0][2]["Content-Type"], "application/json")
            self.assertIn(b'"messageBody":"Body"', posts[0][3])
            with self.assertRaises(module.SmoobuApiError):
                await api.send_message_to_guest(1, "Subject", "  ")
            self.assertEqual(len([x for x in session.calls if x[0] == "POST"]), 1)
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
