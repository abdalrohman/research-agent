import contextvars

current_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context."""
    current_correlation_id.set(cid)


def get_correlation_id() -> str:
    """Retrieve the correlation ID for the current context."""
    return current_correlation_id.get()
