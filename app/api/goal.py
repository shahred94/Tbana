"""Like goal overlay API."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.widgets.goal import (
    add_like_goal,
    goal_status,
    next_like_goal,
    reset_like_goal,
)


router = APIRouter(
    prefix="/api/goal",
    tags=[
        "Goal"
    ],
)


class GoalAddRequest(BaseModel):

    count: int = 0
    user: str = "Dashboard"


@router.get("/status")
def read_goal_status():
    """Return current like goal progress."""

    return goal_status()


@router.post("/reset")
def reset_goal():
    """Reset progress and restart from the configured goal step."""

    reset_like_goal()
    return goal_status()


@router.post("/add")
def add_goal_likes(
    request: GoalAddRequest,
):
    """Add likes manually, useful for tests and corrections."""

    add_like_goal(
        request.count,
        request.user,
    )
    return goal_status()


@router.post("/next")
def advance_goal():
    """Advance the next target by one configured goal step."""

    next_like_goal()
    return goal_status()
