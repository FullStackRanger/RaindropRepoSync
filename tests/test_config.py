"""
Tests for configuration module.
"""

from src.medium_digest import config


def test_config_has_topics():
    """Test that TOPICS is defined and not empty."""
    assert hasattr(config, "TOPICS")
    assert len(config.TOPICS) > 0


def test_lookback_days_positive():
    """Test that LOOKBACK_DAYS is a positive integer."""
    assert hasattr(config, "LOOKBACK_DAYS")
    assert config.LOOKBACK_DAYS > 0
