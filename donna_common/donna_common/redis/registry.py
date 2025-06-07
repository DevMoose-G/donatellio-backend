from typing import Awaitable, Callable

from donna_common.redis.types import Action

HANDLERS: dict[str, Callable[[Action], Awaitable[None]]] = {}


def on_action(action_type: str):
    def decorator(fn: Callable[[Action], Awaitable[None]]):
        HANDLERS[action_type] = fn
        return fn

    return decorator
