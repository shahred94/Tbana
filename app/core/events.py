"""Shared event models."""

from typing import Any
from pydantic import BaseModel, Field


class LiveEvent(BaseModel):
    """A normalized live event."""

    event_type: str = Field(default="unknown")
    user: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LiveEvent":
        """Create event from raw payload."""
        return cls(
            event_type=str(
                payload.get("event_type", "unknown")
            ),
            user=payload.get("user"),
            data=dict(
                payload.get("data", {})
            ),
        )