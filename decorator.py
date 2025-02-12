import asyncio
import functools
import inspect
import logging
import os
from time import perf_counter

from constant import STORE_FOLDER
from correlation import get_correlation_id


def add_file_logging(cid: str):
    log_filename = f"{STORE_FOLDER}/{cid}.log"
    os.makedirs(os.path.dirname(log_filename) or ".", exist_ok=True)
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s - [%(correlation_id)s] - %(funcName)s - %(message)s")
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)
    return file_handler


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s - [%(correlation_id)s] - %(funcName)s - %(message)s",
    )
    log = logging.getLogger(__name__)
    log.propagate = True

    if log.hasHandlers():
        log.handlers.clear()

    # Filter to inject the current correlation id into log records.
    class CorrelationIDFilter(logging.Filter):
        def filter(self, record):
            record.correlation_id = get_correlation_id()
            return True

    # Add filter to all handlers
    for handler in logging.root.handlers:
        handler.addFilter(CorrelationIDFilter())

    def trace_decorator(func):
        @functools.wraps(func)
        async def async_wrapped(*args, **kwargs):
            return await _trace_logic(func, *args, **kwargs)

        @functools.wraps(func)
        def sync_wrapped(*args, **kwargs):
            return _trace_logic(func, *args, **kwargs)

        def _trace_logic(original_func, *args, **kwargs):
            # Determine if it's an instance method
            is_method = "self" in inspect.signature(original_func).parameters

            args_to_log = args[1:] if is_method else args
            input_params = ", ".join(repr(arg) for arg in args_to_log if arg is not None)
            input_kwargs = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            all_inputs = ", ".join(filter(None, [input_params, input_kwargs]))
            start_time = perf_counter()

            try:
                log.debug(f"Entering {original_func.__qualname__}({all_inputs})", stacklevel=3)
                log.info(f"Running {original_func.__qualname__}", stacklevel=3)

                result = original_func(*args, **kwargs)

                if inspect.iscoroutine(result):

                    async def await_and_log():
                        output = await result
                        duration = perf_counter() - start_time
                        log.info(f"Completed {original_func.__qualname__} in {duration:.2f}s", stacklevel=3)
                        return output

                    return await_and_log()
                else:
                    duration = perf_counter() - start_time
                    log.info(f"Completed {original_func.__qualname__} in {duration:.2f}s", stacklevel=3)
                    return result
            except Exception as e:
                duration = perf_counter() - start_time
                log.error(f"Failed {original_func.__qualname__} in {duration:.2f}s: {e}", exc_info=True, stacklevel=3)
                raise

        return async_wrapped if inspect.iscoroutinefunction(func) else sync_wrapped

    return log, trace_decorator


# Initialize global logging and trace_decorator
log, trace_decorator = setup_logging()


def retry(max_retries=3, delay=1, backoff=2, exceptions=(Exception,)):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries (int): Maximum number of attempts.
        delay (int or float): Initial delay between retries in seconds.
        backoff (int or float): Multiplier applied to delay after each retry.
        exceptions (tuple): Exception types that trigger a retry.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        log.error(f"Retry] Final attempt {attempt} failed for {func.__name__}: {e}", exc_info=True)
                        raise
                    log.warning(
                        f"[Retry] Attempt {attempt} for {func.__name__} failed with error: {e}. Retrying in {current_delay} seconds..."
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

        return wrapper

    return decorator
