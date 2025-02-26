import time
import asyncio
import functools
from collections import deque
from typing import Callable, TypeVar, cast, Any, Deque, Optional, Union, Coroutine

T = TypeVar("T")
AsyncT = TypeVar("AsyncT", bound=Coroutine)


class RateLimitedError(Exception):
    """异常：当函数调用因超出频率限制而被拒绝时抛出"""

    def __init__(self, cooldown_remaining: float):
        self.cooldown_remaining = cooldown_remaining
        super().__init__(f"Rate limited, cooldown remaining: {cooldown_remaining:.2f}s")


class RateLimiter:
    """根据最近的调用频率自动调整冷却时间的限速器"""

    def __init__(self, period: float, multiplier: float):
        """
        初始化速率限制器

        Args:
            period: 跟踪调用历史的时间窗口（秒）(P)
            multiplier: 冷却时间计算的比例因子 (k)
        """
        self.period = period
        self.multiplier = multiplier
        self.call_history: Deque[float] = deque()
        self.last_call_time = 0.0

    def calculate_cooldown(self) -> float:
        """根据最近的调用频率计算冷却时间"""
        # 清理过期的时间戳
        current_time = time.time()
        while self.call_history and current_time - self.call_history[0] > self.period:
            self.call_history.popleft()

        # 计算N（周期内的调用次数）
        n = len(self.call_history)

        # 计算冷却时间: N/P*k
        if n == 0:
            return 0.0
        return (n / self.period) * self.multiplier

    def record_call(self) -> None:
        """记录当前调用"""
        current_time = time.time()
        self.call_history.append(current_time)
        self.last_call_time = current_time


def ratelimit(
    period: float = None,
    multiplier: float = None,
    limiter: Optional[RateLimiter] = None,
    on_limit_exceeded: Optional[Callable[..., Any]] = None,
    throw_on_limit: bool = False,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    同步函数的装饰器：基于最近调用频率限制函数调用

    Args:
        period: 跟踪调用历史的时间窗口（秒）(P)
        multiplier: 冷却时间计算的比例因子 (k)
        limiter: 可选的外部提供的RateLimiter实例
        on_limit_exceeded: 当速率限制被超过时调用的回调函数
        throw_on_limit: 如果为True，当速率限制被超过时，立即抛出RateLimitedError而不是等待

    Returns:
        具有速率限制功能的装饰函数
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        nonlocal limiter
        if limiter is None:
            if period is None or multiplier is None:
                raise ValueError(
                    "Either 'limiter' or both 'period' and 'multiplier' must be provided"
                )
            limiter = RateLimiter(period, multiplier)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            current_time = time.time()

            # 计算冷却时间
            cooldown = limiter.calculate_cooldown()
            time_since_last_call = current_time - limiter.last_call_time

            # 如果自上次调用以来的时间不够
            if time_since_last_call < cooldown:
                wait_time = cooldown - time_since_last_call

                if throw_on_limit:
                    if on_limit_exceeded is not None:
                        on_limit_exceeded(*args, wait_time=wait_time, **kwargs)
                    raise RateLimitedError(wait_time)

                if on_limit_exceeded is not None:
                    on_limit_exceeded(*args, wait_time=wait_time, **kwargs)

                time.sleep(wait_time)

            # 记录此次调用
            limiter.record_call()

            return func(*args, **kwargs)

        return cast(Callable[..., T], wrapper)

    return decorator


def async_ratelimit(
    period: float = None,
    multiplier: float = None,
    limiter: Optional[RateLimiter] = None,
    on_limit_exceeded: Optional[Callable[..., Any]] = None,
    throw_on_limit: bool = False,
) -> Callable[[Callable[..., AsyncT]], Callable[..., AsyncT]]:
    """
    异步函数的装饰器：基于最近调用频率限制函数调用

    Args:
        period: 跟踪调用历史的时间窗口（秒）(P)
        multiplier: 冷却时间计算的比例因子 (k)
        limiter: 可选的外部提供的RateLimiter实例
        on_limit_exceeded: 当速率限制被超过时调用的回调函数
        throw_on_limit: 如果为True，当速率限制被超过时，立即抛出RateLimitedError而不是等待

    Returns:
        具有速率限制功能的异步装饰函数
    """

    def decorator(func: Callable[..., AsyncT]) -> Callable[..., AsyncT]:
        nonlocal limiter
        if limiter is None:
            if period is None or multiplier is None:
                raise ValueError(
                    "Either 'limiter' or both 'period' and 'multiplier' must be provided"
                )
            limiter = RateLimiter(period, multiplier)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_time = time.time()

            # 计算冷却时间
            cooldown = limiter.calculate_cooldown()
            time_since_last_call = current_time - limiter.last_call_time

            # 如果自上次调用以来的时间不够
            if time_since_last_call < cooldown:
                wait_time = cooldown - time_since_last_call

                if throw_on_limit:
                    if on_limit_exceeded is not None:
                        if asyncio.iscoroutinefunction(on_limit_exceeded):
                            await on_limit_exceeded(
                                *args, wait_time=wait_time, **kwargs
                            )
                        else:
                            on_limit_exceeded(*args, wait_time=wait_time, **kwargs)
                    raise RateLimitedError(wait_time)

                if on_limit_exceeded is not None:
                    if asyncio.iscoroutinefunction(on_limit_exceeded):
                        await on_limit_exceeded(*args, wait_time=wait_time, **kwargs)
                    else:
                        on_limit_exceeded(*args, wait_time=wait_time, **kwargs)

                await asyncio.sleep(wait_time)

            # 记录此次调用
            limiter.record_call()

            return await func(*args, **kwargs)

        return cast(Callable[..., AsyncT], wrapper)

    return decorator
