"""The stable routing result used by conversation scenarios."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class Intent(StrEnum):
    SALES = "sales"
    SUPPORT = "support"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: Intent
    confidence: float

    def __post_init__(self) -> None:
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence должен быть конечным числом от 0 до 1")
