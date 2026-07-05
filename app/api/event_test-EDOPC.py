"""TBana Stream Event Test API."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.events import LiveEvent
from app.rules.event_engine import event_engine
from app.actions.manager import action_manager


router = APIRouter()


class EventTestRequest(BaseModel):
    event_type: str
    user: str = "Dashboard Test"
    trigger_value: str = ""
    gift_name: str = ""
    count: int = 1
    coins: int = 0


@router.post("/test/event")
def test_event(
    request: EventTestRequest,
):
    """Test dynamic event."""

    data = {}


    if request.event_type.lower() == "gift":

        data = {
            "gift_name": request.gift_name or request.trigger_value or "Rose",
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


    elif request.event_type.lower() == "gift_min_coins":

        data = {
            "gift_name": request.gift_name or "Dashboard Test Gift",
            "count": request.count,
            "coins": request.coins or request.count,
            "diamond_count": request.coins or request.count,
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
