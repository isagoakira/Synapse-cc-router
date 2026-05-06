"""
Exception definitions for CC Router.
"""


class RouterError(Exception):
    """Base exception for router-level errors."""

    pass


class AdapterError(Exception):
    """Base exception for adapter-related errors."""

    pass


class CCExecutorError(Exception):
    """Exception raised when CC Executor encounters errors."""

    pass


class RegistrationError(Exception):
    """Exception raised when registration operations fail."""

    pass


class RoutingError(RouterError):
    """Exception raised when routing decision fails."""

    pass


class TimeoutError(RouterError):
    """Exception raised when task execution times out."""

    pass
