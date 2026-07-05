"""Local feedback submission endpoint."""

from datetime import datetime
import json
from pathlib import Path
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.auth.email import send_feedback_email
from app.auth.service import (
    SubscriptionError,
    current_user,
)
from app.core.config import settings
from app.core.paths import data_path


router = APIRouter(
    prefix="/api/feedback",
    tags=["Feedback"],
)

FEEDBACK_RECIPIENT = "shahred94@gmail.com"

FEEDBACK_CATEGORIES = {
    "Bug Report",
    "Feature Request",
    "UI Improvement",
    "Other",
}


class FeedbackRequest(BaseModel):
    category: str
    subject: str = Field(max_length=200)
    description: str = Field(max_length=5000)
    email: str
    plan: str = ""
    created_at: str = ""

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        clean_value = value.strip()
        if clean_value not in FEEDBACK_CATEGORIES:
            raise ValueError("Invalid feedback category.")
        return clean_value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        clean_value = value.strip().lower()
        if (
            len(clean_value) > 254
            or
            not re.fullmatch(
                r"[^@\s]+@[^@\s]+\.[^@\s]+",
                clean_value,
            )
        ):
            raise ValueError("A valid email is required.")
        return clean_value

    @field_validator("subject")
    @classmethod
    def require_subject(cls, value: str) -> str:
        clean_value = " ".join(
            value.splitlines()
        ).strip()
        if not clean_value:
            raise ValueError("This field is required.")
        return clean_value

    @field_validator("description")
    @classmethod
    def require_text(cls, value: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("This field is required.")
        return clean_value


def feedback_filename(
    folder: Path,
    submitted_at: datetime,
) -> Path:
    """Return a timestamped filename without overwriting a submission."""

    stem = submitted_at.strftime(
        "%Y-%m-%d_%H%M%S_feedback"
    )
    target = folder / f"{stem}.json"
    counter = 2

    while target.exists():
        target = folder / f"{stem}_{counter}.json"
        counter += 1

    return target


@router.post("")
def submit_feedback(
    payload: FeedbackRequest,
    request: Request,
):
    """Save a validated feedback submission to the local data folder."""

    submitted_at = datetime.now().astimezone()
    try:
        user = current_user(
            request
        )
    except SubscriptionError:
        user = None

    plan = str(
        (
            user.get("plan", "")
            if user
            else payload.plan
        )
        or
        "guest"
    ).strip().lower()
    if plan not in {
        "guest",
        "free",
        "pro",
    }:
        plan = "guest"

    feedback = {
        "category": payload.category,
        "subject": payload.subject,
        "description": payload.description,
        "email": (
            user.get("email", "")
            if user
            else payload.email.strip()
        ),
        "plan": plan.title(),
        "app_version": settings.app_version,
        "created_at": submitted_at.isoformat(),
    }

    folder = data_path(
        "feedback"
    )
    folder.mkdir(
        parents=True,
        exist_ok=True,
    )
    target = feedback_filename(
        folder,
        submitted_at,
    )
    temporary = target.with_suffix(
        ".tmp"
    )
    temporary.write_text(
        json.dumps(
            feedback,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(
        target
    )

    try:
        send_feedback_email(
            FEEDBACK_RECIPIENT,
            feedback,
        )
    except Exception:
        return JSONResponse(
            status_code=502,
            content={
                "error": "FEEDBACK_EMAIL_FAILED",
                "message": (
                    "Your feedback was saved locally, but email delivery "
                    "failed. Please try again later."
                ),
                "saved": True,
                "filename": target.name,
            },
        )

    return {
        "message": "Thank you! Your feedback has been submitted.",
        "filename": target.name,
    }
