"""
Tests: Budget Manager
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.budget_manager import (
    BudgetManager,
    estimate_script_generation_cost,
    estimate_video_generation_cost,
    estimate_tts_cost,
)


def test_estimate_script_generation_cost():
    # If None, returns small approximate cost
    assert estimate_script_generation_cost(None) > 0.0
    # 1 million tokens at $0.30 per 1M tokens
    cost = estimate_script_generation_cost(1_000_000)
    assert abs(cost - 0.30) < 1e-5


def test_estimate_video_generation_cost():
    # 10 seconds at $0.10/sec = $1.00
    cost = estimate_video_generation_cost(10.0)
    assert abs(cost - 1.00) < 1e-5


def test_estimate_tts_cost():
    # 1M characters at $16.00 = $16.00
    cost = estimate_tts_cost(1_000_000)
    assert abs(cost - 16.00) < 1e-5
    # 1,000 characters = 0.016
    cost_1k = estimate_tts_cost(1_000)
    assert abs(cost_1k - 0.016) < 1e-5


@pytest.mark.asyncio
async def test_budget_manager_can_generate_under_budget():
    settings = MagicMock()
    settings.max_daily_spend_usd = 5.0
    settings.max_daily_videos = 10

    session = AsyncMock()
    # Mock sum query returns 2.0, count query returns 3
    mock_spend = MagicMock()
    mock_spend.scalar_one.return_value = 2.0
    mock_count = MagicMock()
    mock_count.scalar_one.return_value = 3
    session.execute.side_effect = [mock_spend, mock_count]

    mgr = BudgetManager(session, settings)
    can_gen, reason = await mgr.can_generate()
    assert can_gen is True
    assert reason == ""


@pytest.mark.asyncio
async def test_budget_manager_exceeded_spend():
    settings = MagicMock()
    settings.max_daily_spend_usd = 5.0
    settings.max_daily_videos = 10

    session = AsyncMock()
    mock_spend = MagicMock()
    mock_spend.scalar_one.return_value = 5.50
    session.execute.return_value = mock_spend

    mgr = BudgetManager(session, settings)
    can_gen, reason = await mgr.can_generate()
    assert can_gen is False
    assert "Daily budget exhausted" in reason


@pytest.mark.asyncio
async def test_budget_manager_exceeded_video_count():
    settings = MagicMock()
    settings.max_daily_spend_usd = 50.0
    settings.max_daily_videos = 5

    session = AsyncMock()
    mock_spend = MagicMock()
    mock_spend.scalar_one.return_value = 1.0
    mock_count = MagicMock()
    mock_count.scalar_one.return_value = 5
    session.execute.side_effect = [mock_spend, mock_count]

    mgr = BudgetManager(session, settings)
    can_gen, reason = await mgr.can_generate()
    assert can_gen is False
    assert "Daily video limit reached" in reason
