import functools
import asyncio


def timeout(seconds=5, timeout_callback=None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                if timeout_callback:
                    return await timeout_callback(*args, **kwargs)
                else:
                    return None

        return wrapper

    return decorator
