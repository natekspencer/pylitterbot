from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from .enums import LitterBoxStatus
from .utils import pluralize


@dataclass
class Activity:
    """Represents a historical activity for a Litter-Robot"""

    timestamp: datetime
    unit_status: Optional[LitterBoxStatus] = LitterBoxStatus.READY
    count: Optional[int] = 1

    def __str__(self) -> str:
        return f"{self.timestamp.isoformat()}: {self.unit_status.text} - {pluralize('cycle', self.count)}"


@dataclass
class Insight:
    """Represents a summary and count of daily cycles per day for a Litter-Robot"""

    total_cycles: int
    average_cycles: float
    cycle_history: Iterable[Activity]

    @property
    def total_days(self) -> int:
        return len(self.cycle_history)

    def __str__(self) -> str:
        return f"Completed {pluralize('cycle',self.total_cycles)} averaging {self.average_cycles} cycles per day over the last {pluralize('day',self.total_days)}"
