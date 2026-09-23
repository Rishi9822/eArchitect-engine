"""
API package — routes and error handling.
"""
from .errors import EngineError, engine_error_handler

__all__ = ["EngineError", "engine_error_handler"]
