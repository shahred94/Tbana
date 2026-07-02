"""LiveTrigger Event Test API."""

import time

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.test_timing import normalize_test_delay
from app.core.events import LiveEvent
from app.rules.event_engine import event_engine
from app.actions.manager import action_manager


router = APIRouter()


class EventTestRequest(BaseModel):
    event_type: str
    user: str = "Dashboard Test"
    trigger_value: str = ""
    count: int = 1
    delay_seconds: float = 0


@router.post("/test/event")
def test_event(
    request: EventTestRequest,
):
    """Test dynamic event."""

    delay_seconds = normalize_test_delay(
        request.delay_seconds
    )
    if delay_seconds:
        time.sleep(
            delay_seconds
        )

    data = {}


    if request.event_type.lower() == "gift":

        data = {
            "gift_name": request.trigger_value,
            "count": request.count,
        }


    elif request.event_type.lower() == "comment":

        data = {
            "comment": request.trigger_value,
        }


    elif request.event_type.lower() == "like":

        data = {
            "count": request.count,
        }


    event = LiveEvent(
        event_type=request.event_type,
        user=request.user,
        data=data,
    )


    result = event_engine.process(
        event
    )


# Actions are executed by Event Engine / Smart Queue


    return {
        "message": "Event test executed",
        "event": event.model_dump(),
        "result": result,
    }
