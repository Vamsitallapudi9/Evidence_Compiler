"""Content-addressed identifiers.

IDs are derived from the content they identify, so the same source material always
produces the same evidence IDs and any tampering with stored content is detectable.
"""

import hashlib
import json
import uuid
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def content_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(_canonical(parts).encode()).hexdigest()
    return f"{prefix}_{digest[:16]}"


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def random_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
