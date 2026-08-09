"""Tick-feed integrity checks. The validator reports anomalies and never cleans them."""

from demo_beta.data.validation import DataQualityViolation, TickFeedValidator

__all__ = ["DataQualityViolation", "TickFeedValidator"]
