"""Application settings API."""

from fastapi import APIRouter

from pydantic import BaseModel


from app.storage.sqlite_store import (
    get_setting,
    set_setting,
)


router = APIRouter(
    prefix="/api",
    tags=[
        "Settings"
    ],
)


# ==========================
# Models
# ==========================


class SettingUpdate(BaseModel):

    key: str

    value: str


# ==========================
# API
# ==========================


@router.get("/settings/{key}")
def read_setting(
    key: str,
):

    return {

        "key": key,

        "value": get_setting(
            key
        )

    }


@router.put("/settings")
def update_setting(
    setting: SettingUpdate,
):

    set_setting(
        setting.key,
        setting.value,
    )


    return {

        "message":
        "Setting updated",

        "key":
        setting.key,

        "value":
        setting.value,

    }