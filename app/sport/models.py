from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Sport:
    id: int
    name: str
    special: bool


@dataclass(slots=True)
class TrainingSlot:
    """A concrete dated training session from /calendar/trainings."""

    id: int
    group_id: int
    title: str
    start: datetime
    end: datetime
    can_check_in: bool
    checked_in: bool


@dataclass(slots=True)
class TrainingInfo:
    """Detail from /training/<id>."""

    id: int
    group_id: int
    title: str
    start: datetime
    end: datetime
    load: int
    capacity: int
    can_check_in: bool
    checked_in: bool

    @property
    def free_places(self) -> int:
        return self.capacity - self.load
