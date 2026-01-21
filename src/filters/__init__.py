"""
Filter system for media selection.

Provides pluggable filter abstractions for determining which messages
should be downloaded based on configurable criteria.
"""

from src.filters.base import BaseFilter
from src.filters.extension import ExtensionFilter
from src.filters.size import SizeFilter
from src.filters.date import DateFilter
from src.filters.pattern import PatternFilter
from src.filters.composite import CompositeFilter

__all__ = [
    "BaseFilter",
    "ExtensionFilter",
    "SizeFilter",
    "DateFilter",
    "PatternFilter",
    "CompositeFilter",
]
