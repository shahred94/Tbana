"""LiveTrigger Event Simulator API."""

import asyncio

from fastapi import APIRouter

from app.api.test_timing import normalize_test_delay
from app.core.events import LiveEvent
from app.rules.event_engine import event_engine


router = APIRouter()


@router.post(
    "/simulate"
)
async def simulate_event(
    payload: dict,
):

    """Simulate a TikTok event."""

    delay_seconds = normalize_test_delay(
        payload.pop(
            "delay_seconds",
            0,
        )
    )

    if delay_seconds:
        await asyncio.sleep(
            delay_seconds
        )

    payload.setdefault(
        "data",
        {},
    )

    payload[
        "data"
    ][
        "_simulator"
    ] = True

    event = LiveEvent.from_payload(
        payload
    )


    result = event_engine.process(
        event
    )


    return result
