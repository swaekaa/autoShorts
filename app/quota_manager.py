"""
Quota Manager
=============
Tracks API usage across providers, enforces cooldowns, classifies errors,
and provides a unified interface for checking whether generation can proceed.

Design principles:
- Quota state is persisted to PostgreSQL (quota_events table)
- Reset times are NEVER invented – we use provider Retry-After headers or
  a configurable cooldown, then recheck with a real lightweight API call
- Each provider has an independent state machine
"""

from __future__ import annotations

import asyncio
import enum
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuotaEvent, QuotaEventType, ServiceProvider
from app.logging_config import get_logger

logger = get_logger(__name__)


class QuotaState(str, enum.Enum):
    READY = "ready"
    GENERATING = "generating"
    COOLDOWN = "cooldown"
    QUOTA_EXHAUSTED = "quota_exhausted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NEEDS_ATTENTION = "needs_attention"
    DISABLED = "disabled"


# Per-provider runtime state (in-memory cache, truth is in DB)
_provider_states: dict[ServiceProvider, QuotaState] = {}
_provider_cooldown_until: dict[ServiceProvider, datetime] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QuotaManager:
    """
    Manages quota state for all API providers.
    Instances are lightweight – state is loaded from DB on demand.
    """

    def __init__(self, session: AsyncSession, settings: Any):
        self._db = session
        self._settings = settings

    async def record_event(
        self,
        provider: ServiceProvider,
        event_type: QuotaEventType,
        model_id: str | None = None,
        error_code: str | None = None,
        observed_usage: dict | None = None,
        retry_after_seconds: int | None = None,
        estimated_cost_usd: float | None = None,
    ) -> None:
        """Persist a quota event and update in-memory state."""
        event = QuotaEvent(
            provider=provider,
            model_id=model_id,
            event_type=event_type,
            error_code=error_code,
            observed_usage=observed_usage,
            retry_after_seconds=retry_after_seconds,
            estimated_cost_usd=estimated_cost_usd,
        )
        self._db.add(event)
        await self._db.flush()

        # Update in-memory state
        if event_type == QuotaEventType.QUOTA_EXCEEDED:
            _provider_states[provider] = QuotaState.QUOTA_EXHAUSTED
            cooldown_secs = retry_after_seconds or (self._settings.quota_cooldown_minutes * 60)
            _provider_cooldown_until[provider] = _now() + timedelta(seconds=cooldown_secs)
            logger.warning(
                "Quota exhausted",
                extra={
                    "provider": provider.value,
                    "cooldown_until": _provider_cooldown_until[provider].isoformat(),
                    "retry_after_seconds": cooldown_secs,
                },
            )
        elif event_type == QuotaEventType.RATE_LIMITED:
            _provider_states[provider] = QuotaState.COOLDOWN
            cooldown_secs = retry_after_seconds or 60
            _provider_cooldown_until[provider] = _now() + timedelta(seconds=cooldown_secs)
            logger.info(
                "Rate limited – entering cooldown",
                extra={"provider": provider.value, "cooldown_seconds": cooldown_secs},
            )
        elif event_type == QuotaEventType.SUCCESS:
            _provider_states[provider] = QuotaState.READY
        elif event_type == QuotaEventType.COOLDOWN_ENDED:
            _provider_states[provider] = QuotaState.READY
            _provider_cooldown_until.pop(provider, None)

    async def get_state(self, provider: ServiceProvider) -> QuotaState:
        """Return current effective quota state, accounting for cooldown expiry."""
        # Check if cooldown has expired
        cooldown_until = _provider_cooldown_until.get(provider)
        if cooldown_until and _now() >= cooldown_until:
            logger.info(
                "Cooldown expired – resetting to READY",
                extra={"provider": provider.value},
            )
            _provider_states[provider] = QuotaState.READY
            _provider_cooldown_until.pop(provider, None)
            await self.record_event(provider, QuotaEventType.COOLDOWN_ENDED)

        return _provider_states.get(provider, QuotaState.READY)

    async def can_generate(self, provider: ServiceProvider) -> bool:
        state = await self.get_state(provider)
        return state in (QuotaState.READY, QuotaState.GENERATING)

    async def get_cooldown_remaining(self, provider: ServiceProvider) -> int:
        """Return remaining cooldown seconds (0 if none)."""
        cooldown_until = _provider_cooldown_until.get(provider)
        if not cooldown_until:
            return 0
        remaining = (cooldown_until - _now()).total_seconds()
        return max(0, int(remaining))

    async def get_daily_spend(self, session: AsyncSession) -> float:
        """Sum estimated costs from today's quota events."""
        today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await session.execute(
            select(func.sum(QuotaEvent.estimated_cost_usd)).where(
                QuotaEvent.event_timestamp >= today_start,
                QuotaEvent.estimated_cost_usd.is_not(None),
            )
        )
        total = result.scalar_one_or_none()
        return float(total or 0.0)

    async def get_all_states(self) -> dict[str, str]:
        result = {}
        for provider in ServiceProvider:
            state = await self.get_state(provider)
            result[provider.value] = state.value
        return result


def classify_api_error(error: Exception) -> tuple[QuotaEventType, str | None, int | None]:
    """
    Inspect an exception and return (event_type, error_code, retry_after_seconds).
    Works with google-genai and google-api-python-client exceptions.
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Try to extract Retry-After from exception attributes
    retry_after: int | None = None
    if hasattr(error, "retry_delay"):
        retry_after = int(getattr(error, "retry_delay", 0) or 0) or None
    if hasattr(error, "metadata"):
        for item in getattr(error, "metadata", []):
            if hasattr(item, "retry_delay"):
                retry_after = int(item.retry_delay.seconds)
                break

    # Classify by HTTP status / message
    if any(kw in error_str for kw in ("429", "quota", "resource_exhausted", "resourceexhausted")):
        if "quota" in error_str or "resource_exhausted" in error_str:
            return QuotaEventType.QUOTA_EXCEEDED, "RESOURCE_EXHAUSTED", retry_after
        return QuotaEventType.RATE_LIMITED, "RATE_LIMITED", retry_after or 60

    if any(kw in error_str for kw in ("401", "403", "unauthenticated", "permission_denied")):
        return QuotaEventType.ERROR, "AUTH_ERROR", None

    if any(kw in error_str for kw in ("500", "503", "unavailable", "internal")):
        return QuotaEventType.ERROR, "SERVER_ERROR", retry_after or 30

    return QuotaEventType.ERROR, "UNKNOWN", None


async def with_exponential_backoff(
    coro_fn,
    *args,
    max_retries: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 120.0,
    retryable_event_types: tuple[QuotaEventType, ...] = (
        QuotaEventType.RATE_LIMITED,
        QuotaEventType.ERROR,
    ),
    **kwargs,
):
    """
    Run an async coroutine with exponential backoff + jitter.
    Raises the last exception if all retries are exhausted.
    Does NOT retry QUOTA_EXCEEDED or AUTH_ERROR.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:
            event_type, error_code, retry_after = classify_api_error(exc)

            # Non-retryable errors
            if event_type == QuotaEventType.QUOTA_EXCEEDED:
                raise
            if error_code == "AUTH_ERROR":
                raise

            last_exc = exc
            if attempt == max_retries:
                break

            # Calculate delay
            if retry_after:
                delay = float(retry_after)
            else:
                delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.2)
            total_delay = delay + jitter

            logger.warning(
                "Retryable error – backing off",
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "delay_seconds": round(total_delay, 1),
                    "error": str(exc)[:200],
                },
            )
            await asyncio.sleep(total_delay)

    raise last_exc  # type: ignore[misc]
