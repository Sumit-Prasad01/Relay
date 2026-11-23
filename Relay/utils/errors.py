"""Complete error taxonomy matching implementation plan Section 7.4."""

from typing import Any, Dict, Optional


class RelayError(Exception):
    """Base exception for all Relay Agent errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# Authentication & Authorization
class AuthenticationError(RelayError):
    """Invalid or missing API key, credentials, or authentication token."""
    pass


# Rate Limit & Quotas
class RateLimitError(RelayError):
    """Provider rate limit or throughput throttled."""
    pass


class QuotaError(RelayError):
    """Provider billing, balance or quota exhausted."""
    pass


# Model Discovery & Capability
class ModelNotFoundError(RelayError):
    """Specified model ID is not available or supported by provider."""
    pass


class UnsupportedCapabilityError(RelayError):
    """Model does not support a required capability (e.g., tool calling, streaming)."""
    pass


# Context & Token Budget
class ContextOverflowError(RelayError):
    """Request exceeded model or configured context window limit."""
    pass


# Network & Transport
class NetworkTimeoutError(RelayError):
    """Network connection timeout or connection failure."""
    pass


# Tool Execution
class InvalidToolArgumentsError(RelayError):
    """Tool invocation arguments failed schema validation."""
    pass


class ToolExecutionError(RelayError):
    """Tool handler raised an error during execution."""
    pass


# Permissions & Sandboxing
class PermissionDeniedError(RelayError):
    """Operation was blocked by security policy or rejected by the user."""
    pass


# Lifecycle & User Interrupt
class UserCancelledError(RelayError):
    """Task or operation was cancelled by the user."""
    pass


# Internal / System
class InternalApplicationError(RelayError):
    """Unexpected application error or failure in runtime services."""
    pass


class DatabaseError(RelayError):
    """SQLite or schema migration failure."""
    pass


class ConfigurationError(RelayError):
    """Configuration syntax, file parsing or validation failure."""
    pass
