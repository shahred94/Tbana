"""TBana Stream API routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.events import LiveEvent
from app.rules.engine import rules_engine
from app.actions.manager import action_manager
from app.queue.manager import (
    gift_queue_manager,
)
from app.core.activity import activity_feed

from app.storage.sqlite_store import (
    get_all_gift_rules,
    add_gift_rule,
    update_gift_rule,
    update_gift_status,
    delete_gift_rule,
)


router = APIRouter()


class GiftCreate(BaseModel):
    gift_name: str
    sound: str
    overlay: str


class GiftStatus(BaseModel):
    enabled: bool


class TestGiftRequest(BaseModel):
    user: str
    gift_name: str
    count: int = 1


@router.get("/status")
def get_status():

    return {
        "application": "TBana Stream",
        "status": "running",
    }
    
@router.get("/queue/status")
def get_queue_status():

    return {
        "queues": (
            gift_queue_manager.get_status()
        ),
        "paused": gift_queue_manager.paused,
    }


@router.post("/queue/pause")
def pause_queue():
    gift_queue_manager.pause()
    return {"message": "Queue paused"}


@router.post("/queue/resume")
def resume_queue():
    gift_queue_manager.resume()
    return {"message": "Queue resumed"}


@router.delete("/queue")
def clear_all_queues():
    return {
        "message": "Queues cleared",
        "cleared": gift_queue_manager.clear(),
    }


@router.delete("/queue/{gift_name}")
def clear_named_queue(gift_name: str):
    return {
        "message": "Queue cleared",
        "cleared": gift_queue_manager.clear(
            gift_name
        ),
    }


@router.get("/activity/recent")
def get_recent_activity(limit: int = 30):
    return {
        "activity": activity_feed.recent(limit)
    }


@router.delete("/activity/recent")
def clear_recent_activity():
    activity_feed.clear()
    return {"message": "Recent activity cleared"}

@router.get("/gifts")
def get_gifts():

    return {
        "gifts": get_all_gift_rules()
    }


@router.post("/gifts")
def create_gift(
    gift: GiftCreate,
):

    add_gift_rule(
        gift_name=gift.gift_name,
        sound_file=gift.sound,
        overlay=gift.overlay,
    )

    return {
        "message": "Gift created",
        "gift": gift.model_dump(),
    }


@router.put("/gifts/{gift_id}")
def edit_gift(
    gift_id: int,
    gift: GiftCreate,
):

    update_gift_rule(
        gift_id=gift_id,
        gift_name=gift.gift_name,
        sound_file=gift.sound,
        overlay=gift.overlay,
    )

    return {
        "message": "Gift updated",
        "gift_id": gift_id,
        "gift": gift.model_dump(),
    }


@router.put("/gifts/{gift_id}/status")
def change_gift_status(
    gift_id: int,
    status: GiftStatus,
):

    update_gift_status(
        gift_id,
        status.enabled,
    )

    return {
        "message": "Status updated",
        "gift_id": gift_id,
        "enabled": status.enabled,
    }


@router.delete("/gifts/{gift_id}")
def remove_gift(
    gift_id: int,
):

    delete_gift_rule(
        gift_id
    )

    return {
        "message": "Gift deleted",
        "gift_id": gift_id,
    }


@router.post("/test/gift")
def test_gift(
    request: TestGiftRequest,
):

    event = LiveEvent(
        event_type="gift",
        user=request.user,
        data={
            "gift_name": request.gift_name,
            "count": request.count,
        },
    )

    result = rules_engine.process(
        event
    )

    if result["matched"]:

        action_manager.execute(
            result["actions"]
        )

    return {
        "message": "Test executed",
        "event": event.model_dump(),
        "rules": result,
    }
