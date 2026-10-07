"""The stable routing result used by conversation scenarios."""

from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    SALES = "sales"
    SUPPORT = "support"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: Intent
    confidence: float
