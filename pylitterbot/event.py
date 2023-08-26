"""Event handling class for pylitterbot."""
from __future__ import annotations

from abc import ABC
from collections.abc import Callable
from typing import Any

EVENT_UPDATE = "update"


class Event(ABC):
    """Abstract event class properties and methods."""

    _listeners: dict[str, list[Callable]] = {}

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Run all callbacks for an event."""
        for listener in self._listeners.get(event_name, []):
            try:
                listener(*args, **kwargs)
            except:  # pragma: no cover # pylint: disable=bare-except # noqa: E722
                pass

    def on(  # pylint: disable=invalid-name
        self, event_name: str, callback: Callable
    ) -> Callable:
        """Register an event callback."""
        listeners: list = self._listeners.setdefault(event_name, [])
        listeners.append(callback)

        def unsubscribe() -> None:
            """Unsubscribe listeners."""
            if callback in listeners:
                listeners.remove(callback)

        return unsubscribe
