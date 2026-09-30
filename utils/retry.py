import time
import random
import functools
from typing import Callable, Any, Type, Tuple
from .logging import get_logger

logger = get_logger("retry_handler")

PERMANENT_ERROR_CODES = {400, 401, 403, 404, 422}
TRANSIENT_ERROR_CODES = {408, 429, 500, 502, 503, 504}

class PermanentPipelineError(Exception):
    """Errors that should NOT be retried (e.g. invalid credentials, bad model name)."""
    pass

class TransientPipelineError(Exception):
    """Errors that can safely be retried (e.g. temporary 503, network glitch)."""
    pass

def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_on: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator for retrying operations with exponential backoff and jitter.
    Halts immediately on PermanentPipelineError.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except PermanentPipelineError:
                    raise
                except retry_on as exc:
                    last_exception = exc
                    if attempt == max_retries:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {exc}")
                        raise
                    
                    sleep_time = delay * (1.0 + (random.uniform(-0.1, 0.1) if jitter else 0.0))
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_retries} failed ({exc}). Retrying in {sleep_time:.2f}s..."
                    )
                    time.sleep(max(0.1, sleep_time))
                    delay *= backoff_factor

            if last_exception:
                raise last_exception
        return wrapper
    return decorator
