from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any


CURSOR_VERSION = 1


def encode_cursor(
    created_at: datetime,
    job_id: uuid.UUID,
) -> str:
    payload: dict[str, Any] = {
        "v": CURSOR_VERSION,
        "created_at": created_at.isoformat(),
        "id": str(job_id),
    }

    raw = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(
    cursor: str,
) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))

        payload = json.loads(raw.decode("utf-8"))

        if payload.get("v") != CURSOR_VERSION:
            raise ValueError("Unsupported cursor version")

        created_at = datetime.fromisoformat(payload["created_at"])

        job_id = uuid.UUID(payload["id"])

        return created_at, job_id

    except (
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Invalid pagination cursor") from exc
