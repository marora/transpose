"""Tests for Azure RBAC propagation retry helpers."""

from __future__ import annotations

import pytest
from azure.core.exceptions import HttpResponseError

from transpose.services.azure_rbac_retry import with_rbac_retry


def _forbidden_error() -> HttpResponseError:
    exc = HttpResponseError(
        message="This request is not authorized to perform this operation."
    )
    exc.status_code = 403
    exc.error_code = "AuthorizationPermissionMismatch"
    return exc


class TestWithRbacRetry:
    @pytest.mark.asyncio
    async def test_retries_http_403_until_success(self) -> None:
        attempts = 0
        retry_messages: list[str] = []
        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def flaky_operation() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise _forbidden_error()
            return "ok"

        result = await with_rbac_retry(
            flaky_operation,
            on_retry=retry_messages.append,
            sleep=fake_sleep,
        )

        assert result == "ok"
        assert attempts == 3
        assert sleep_calls == [15, 30]
        assert retry_messages == [
            "⏳ Waiting for RBAC role propagation… (attempt 2/6, sleeping 15s)",
            "⏳ Waiting for RBAC role propagation… (attempt 3/6, sleeping 30s)",
        ]

    @pytest.mark.asyncio
    async def test_non_auth_errors_fail_fast(self) -> None:
        attempts = 0
        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def broken_operation() -> str:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("socket timeout")

        with pytest.raises(RuntimeError, match="socket timeout"):
            await with_rbac_retry(broken_operation, sleep=fake_sleep)

        assert attempts == 1
        assert sleep_calls == []
