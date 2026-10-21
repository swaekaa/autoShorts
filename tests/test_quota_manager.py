"""
Tests: Quota Manager
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.quota_manager import (
    QuotaEventType,
    QuotaManager,
    QuotaState,
    ServiceProvider,
    _provider_states,
    _provider_cooldown_until,
    classify_api_error,
    with_exponential_backoff,
)


def make_settings():
    s = MagicMock()
    s.quota_cooldown_minutes = 65
    return s


def make_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture(autouse=True)
def reset_state():
    """Clear in-memory quota state before each test."""
    _provider_states.clear()
    _provider_cooldown_until.clear()
    yield
    _provider_states.clear()
    _provider_cooldown_until.clear()


@pytest.mark.asyncio
async def test_initial_state_is_ready():
    qm = QuotaManager(make_session(), make_settings())
    state = await qm.get_state(ServiceProvider.GEMINI_VIDEO)
    assert state == QuotaState.READY


@pytest.mark.asyncio
async def test_quota_exceeded_sets_exhausted_state():
    qm = QuotaManager(make_session(), make_settings())
    await qm.record_event(
        provider=ServiceProvider.GEMINI_VIDEO,
        event_type=QuotaEventType.QUOTA_EXCEEDED,
        retry_after_seconds=3600,
    )
    state = await qm.get_state(ServiceProvider.GEMINI_VIDEO)
    assert state == QuotaState.QUOTA_EXHAUSTED


@pytest.mark.asyncio
async def test_cooldown_expires_returns_ready():
    qm = QuotaManager(make_session(), make_settings())
    # Set a cooldown that already expired
    _provider_states[ServiceProvider.GEMINI_VIDEO] = QuotaState.COOLDOWN
    _provider_cooldown_until[ServiceProvider.GEMINI_VIDEO] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    state = await qm.get_state(ServiceProvider.GEMINI_VIDEO)
    assert state == QuotaState.READY


@pytest.mark.asyncio
async def test_can_generate_false_when_quota_exhausted():
    qm = QuotaManager(make_session(), make_settings())
    _provider_states[ServiceProvider.GEMINI_VIDEO] = QuotaState.QUOTA_EXHAUSTED
    _provider_cooldown_until[ServiceProvider.GEMINI_VIDEO] = (
        datetime.now(timezone.utc) + timedelta(hours=1)
    )
    result = await qm.can_generate(ServiceProvider.GEMINI_VIDEO)
    assert result is False


@pytest.mark.asyncio
async def test_can_generate_true_when_ready():
    qm = QuotaManager(make_session(), make_settings())
    result = await qm.can_generate(ServiceProvider.GEMINI_VIDEO)
    assert result is True


def test_classify_quota_exceeded():
    exc = Exception("RESOURCE_EXHAUSTED: Quota exceeded (429)")
    event_type, code, _ = classify_api_error(exc)
    assert event_type == QuotaEventType.QUOTA_EXCEEDED


def test_classify_rate_limited():
    exc = Exception("429 Too Many Requests")
    event_type, code, _ = classify_api_error(exc)
    assert event_type in (QuotaEventType.RATE_LIMITED, QuotaEventType.QUOTA_EXCEEDED)


def test_classify_auth_error():
    exc = Exception("401 Unauthenticated: Invalid API key")
    event_type, code, _ = classify_api_error(exc)
    assert code == "AUTH_ERROR"


def test_classify_server_error():
    exc = Exception("500 Internal Server Error")
    event_type, code, _ = classify_api_error(exc)
    assert event_type == QuotaEventType.ERROR
    assert code == "SERVER_ERROR"


@pytest.mark.asyncio
async def test_exponential_backoff_succeeds_on_first_try():
    call_count = 0

    async def success_fn():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await with_exponential_backoff(success_fn, max_retries=3, base_delay=0.01)
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_exponential_backoff_retries_on_server_error():
    call_count = 0

    async def flaky_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("500 Internal Server Error")
        return "ok"

    result = await with_exponential_backoff(flaky_fn, max_retries=4, base_delay=0.01)
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_exponential_backoff_does_not_retry_quota_exceeded():
    async def quota_fn():
        raise Exception("RESOURCE_EXHAUSTED: Quota exceeded (429)")

    with pytest.raises(Exception, match="RESOURCE_EXHAUSTED"):
        await with_exponential_backoff(quota_fn, max_retries=3, base_delay=0.01)


@pytest.mark.asyncio
async def test_exponential_backoff_exhausts_retries():
    async def always_fail():
        raise Exception("500 Internal Server Error")

    with pytest.raises(Exception):
        await with_exponential_backoff(always_fail, max_retries=2, base_delay=0.01)
