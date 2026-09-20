from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response


MAX_REQUEST_ID_LENGTH = 128


async def request_context_middleware(
    request: Request,
    call_next: Callable[
        [Request],
        Awaitable[Response],
    ],
) -> Response:
    incoming_request_id = request.headers.get(
        "X-Request-ID"
    )

    if (
        incoming_request_id
        and len(incoming_request_id) <= MAX_REQUEST_ID_LENGTH
    ):
        request_id = incoming_request_id
    else:
        request_id = str(uuid.uuid4())

    request.state.request_id = request_id

    started = time.perf_counter()

    response = await call_next(request)

    elapsed = time.perf_counter() - started

    response.headers["X-Request-ID"] = request_id

    response.headers["X-Process-Time"] = (
        f"{elapsed:.6f}"
    )

    return response