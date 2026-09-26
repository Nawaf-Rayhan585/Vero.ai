"""Phase 17: app/rate_limit.py's own logic, tested directly against its dependency
function rather than through the full HTTP stack — matching this project's existing
style for testing a pure algorithm in isolation (e.g. test_counting.py)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.rate_limit import _reset_for_tests, rate_limit


def _fake_request(ip: str = "1.2.3.4"):
    return SimpleNamespace(client=SimpleNamespace(host=ip))


@pytest.fixture(autouse=True)
def _reset():
    _reset_for_tests()
    yield
    _reset_for_tests()


class TestRateLimit:
    def test_allows_requests_up_to_the_limit(self):
        check = rate_limit("test-endpoint", max_requests=3, window_seconds=60)
        request = _fake_request()
        check(request)
        check(request)
        check(request)  # exactly at the limit — still allowed

    def test_rejects_the_request_that_exceeds_the_limit(self):
        check = rate_limit("test-endpoint", max_requests=3, window_seconds=60)
        request = _fake_request()
        check(request)
        check(request)
        check(request)

        with pytest.raises(HTTPException) as exc_info:
            check(request)

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        assert int(exc_info.value.headers["Retry-After"]) > 0

    def test_different_ips_have_independent_buckets(self):
        check = rate_limit("test-endpoint", max_requests=1, window_seconds=60)
        check(_fake_request("1.1.1.1"))
        check(_fake_request("2.2.2.2"))  # a different IP — its own fresh bucket

        with pytest.raises(HTTPException):
            check(_fake_request("1.1.1.1"))  # but the first IP is now over its own limit

    def test_different_endpoint_names_have_independent_buckets(self):
        check_a = rate_limit("endpoint-a", max_requests=1, window_seconds=60)
        check_b = rate_limit("endpoint-b", max_requests=1, window_seconds=60)
        request = _fake_request()

        check_a(request)
        check_b(request)  # same IP, different endpoint name — not affected by endpoint-a's usage

        with pytest.raises(HTTPException):
            check_a(request)

    def test_the_window_resets_after_it_elapses(self):
        check = rate_limit("test-endpoint", max_requests=1, window_seconds=60)
        request = _fake_request()
        check(request)

        with pytest.raises(HTTPException):
            check(request)

        with patch("app.rate_limit.time.monotonic", return_value=__import__("time").monotonic() + 61):
            check(request)  # a new window — allowed again

    def test_a_missing_client_falls_back_to_a_shared_bucket_rather_than_crashing(self):
        check = rate_limit("test-endpoint", max_requests=1, window_seconds=60)
        request = SimpleNamespace(client=None)
        check(request)
        with pytest.raises(HTTPException):
            check(request)
