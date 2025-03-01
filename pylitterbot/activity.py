"""pylitterbot activity and insight classes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .enums import LitterBoxStatus
from .utils import pluralize


@dataclass
class Activity:
    """Represents a historical activity for a Litter-Robot."""

    timestamp: datetime | date
    action: str | LitterBoxStatus

    def __str__(self) -> str:
        """Return self(str)."""
        return f"{self.timestamp.isoformat()}: {self.action.text if isinstance(self.action, LitterBoxStatus) else self.action}"


@dataclass
class Insight:
    """Represents a summary and count of daily cycles per day for a Litter-Robot."""

    total_cycles: int
    average_cycles: float
    cycle_history: list[tuple[date, int]]

    @property
    def total_days(self) -> int:
        """Return total days."""
        return len(self.cycle_history)

    def __str__(self) -> str:
        """Return self(str)."""
        return f"Completed {pluralize('cycle', self.total_cycles)} averaging {self.average_cycles} cycles per day over the last {pluralize('day', self.total_days)}"
