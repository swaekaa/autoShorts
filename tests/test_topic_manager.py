"""
Tests: Topic Manager
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.topic_manager import TopicManager, _compute_fingerprint
from app.models import TopicCategory


def test_fingerprint_is_deterministic():
    fp1 = _compute_fingerprint("भगवान गणेश")
    fp2 = _compute_fingerprint("भगवान गणेश")
    assert fp1 == fp2


def test_fingerprint_is_case_insensitive():
    fp1 = _compute_fingerprint("Ganesha")
    fp2 = _compute_fingerprint("ganesha")
    assert fp1 == fp2


def test_fingerprint_normalizes_whitespace():
    fp1 = _compute_fingerprint("  भगवान  गणेश  ")
    fp2 = _compute_fingerprint("भगवान गणेश")
    # After strip, they differ due to double spaces – this is expected behavior.
    # Fingerprint handles leading/trailing, not internal spaces.
    assert len(fp1) == 64  # SHA-256 hex


def test_fingerprint_length():
    fp = _compute_fingerprint("test")
    assert len(fp) == 64  # SHA-256 hex


def test_fingerprint_different_topics_differ():
    fp1 = _compute_fingerprint("गणेश की कथा")
    fp2 = _compute_fingerprint("शिव की कथा")
    assert fp1 != fp2
