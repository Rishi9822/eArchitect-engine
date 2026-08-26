"""
API package — routes and error handling.
"""
from .routes import v1_router, compat_router
from .errors import EngineError, engine_error_handler
