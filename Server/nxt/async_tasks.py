"""Keep a transaction and its live-state publication together on disconnect."""
from __future__ import annotations

import asyncio


async def complete_before_cancelling(awaitable):
    """Finish an admitted operation before propagating caller cancellation.

    Cancelling an asyncio.to_thread await does not stop its database worker.
    Keep the enclosing world operation alive so it can publish committed state
    and release its lock before socket cleanup saves or removes the player.
    Repeated cancellation requests must not interrupt that completion either.
    """
    operation = asyncio.ensure_future(awaitable)
    cancellation = None
    while True:
        try:
            result = await asyncio.shield(operation)
            break
        except asyncio.CancelledError as error:
            if operation.cancelled():
                raise
            cancellation = error
        except BaseException:
            if cancellation is not None:
                raise cancellation
            raise
    if cancellation is not None:
        raise cancellation
    return result
