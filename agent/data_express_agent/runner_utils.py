from __future__ import annotations

import random


def retry_delay(attempt: int, *, random_value: float | None = None) -> float:
    base = min(60.0, 2.0 ** max(0, attempt))
    jitter = random.random() if random_value is None else random_value
    return base * (0.75 + 0.5 * jitter)
