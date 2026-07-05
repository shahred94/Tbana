"""TBana Stream event simulator API."""

import asyncio

from fastapi import APIRouter, Request

from app.api.test_timing import normalize_test_delay
from app.auth.service import require_authenticated
from app.core.events import LiveEvent
from app.rules.event_engine import event_engine


router = APIRouter()


@router.post(
    "/simulate"
)
async def simulate_event(
    payload: dict,
    request: Request,
):

    """Simulate a TikTok event."""

    require_authenticated(
        request,
        "Please login to simulate events.",
    )

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
