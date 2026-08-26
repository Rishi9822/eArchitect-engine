"""
Shared types used across input and output models.

All geometry uses (x, y) coordinates in metres internally.
"""
from __future__ import annotations

from pydantic import BaseModel


class Coordinate(BaseModel):
    """A 2D point with x, y in metres."""
    x: float
    y: float


class Point(BaseModel):
    """Input point — identical to Coordinate but semantically an input vertex."""
    x: float
    y: float
