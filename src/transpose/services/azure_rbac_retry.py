"""Azure Storage RBAC propagation retry helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

RBAC_RETRY_DELAYS_SECONDS: tuple[int, ...] = (15, 30, 60, 60, 60)
_RBAC_ERROR_TOKENS = frozenset({
    "you do not have the required permissions",
    "storage blob data contributor",
    "authorizationpermissionmismatch",
    "this request is not authorized",
    "insufficientaccountpermissions",
    "status code: 403",
})
_RBAC_ERROR_CODES = frozenset({
    "authorizationpermissionmismatch",
    "authorizationfailure",
    "insufficientaccountpermissions",
})


def is_rbac_propagation_error(exc: Exception) -> bool:
    """Return True when an exception matches transient Azure RBAC lag."""
    status_code = getattr(exc, "status_code", None)
    if status_code == 403:
        return True

    error_code = getattr(exc, "error_code", None)
    if isinstance(error_code, str) and error_code.lower() in _RBAC_ERROR_CODES:
        return True

    message = str(exc).lower()
    return any(token in message for token in _RBAC_ERROR_TOKENS)


async def with_rbac_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    on_retry: Callable[[str], None] | None = None,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    delays_seconds: Sequence[int] = RBAC_RETRY_DELAYS_SECONDS,
) -> T:
    """Retry Azure data-plane auth failures while RBAC propagates."""
    max_attempts = len(delays_seconds) + 1
    attempt = 1

    while True:
        try:
            return await operation()
        except Exception as exc:
            if not is_rbac_propagation_error(exc) or attempt >= max_attempts:
                raise

            sleep_seconds = delays_seconds[attempt - 1]
            if on_retry is not None:
                on_retry(
                    "⏳ Waiting for RBAC role propagation… "
                    f"(attempt {attempt + 1}/{max_attempts}, sleeping {sleep_seconds}s)"
                )
            await sleep(sleep_seconds)
            attempt += 1
