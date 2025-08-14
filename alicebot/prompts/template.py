from typing import Callable, Any
log_func: Callable[[Any], None]
def split_response(message: str) -> list:
    messages = message.split("---split---")
    return [m.strip() for m in messages if m.strip()]

