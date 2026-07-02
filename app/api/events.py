"""LiveTrigger Event API."""

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
)
from pydantic import BaseModel, Field

from app.auth.service import (
    enforce_import_limits,
    enforce_trigger_creation,
    require_authenticated,
    subscription_write_lock,
)

from app.storage.sqlite_store import (
    export_configuration,
    get_events,
    get_event,
    add_event,
    update_event,
    update_event_status,
    delete_event,
    import_configuration,

    get_event_actions,
    add_event_action,
    update_event_action,
    delete_event_action,
)


router = APIRouter(
    prefix="/api",
    tags=[
        "Events"
    ],
)


# ==========================
# Event Models
# ==========================


class EventCreate(BaseModel):

    trigger_type: str
    trigger_value: str
    user_filter: str

    action_type: str
    action_value: str


class EventUpdate(BaseModel):

    trigger_type: str
    trigger_value: str
    user_filter: str

    action_type: str
    action_value: str


class EventStatusUpdate(BaseModel):

    enabled: bool


# ==========================
# Event API
# ==========================


@router.get("/events")
def list_events():

    return {
        "events": get_events()
    }


@router.get("/events/{event_id}")
def read_event(
    event_id: int,
):

    event = get_event(
        event_id
    )


    if event is None:

        return {
            "error": "Event not found"
        }


    return event


@router.post("/events")
def create_event(
    event: EventCreate,
    request: Request,
):

    with subscription_write_lock:

        enforce_trigger_creation(
            request
        )

        add_event(
            event.trigger_type,
            event.trigger_value,
            event.user_filter,
            event.action_type,
            event.action_value,
        )


    return {
        "message": "Event created"
    }


@router.put("/events/{event_id}")
def edit_event(
    event_id: int,
    event: EventUpdate,
):

    update_event(
        event_id,
        event.trigger_type,
        event.trigger_value,
        event.user_filter,
        event.action_type,
        event.action_value,
    )


    return {
        "message": "Event updated"
    }


@router.put("/events/{event_id}/status")
def change_status(
    event_id: int,
    status: EventStatusUpdate,
):

    update_event_status(
        event_id,
        status.enabled,
    )


    return {
        "message": "Status updated"
    }


@router.delete("/events/{event_id}")
def remove_event(
    event_id: int,
):

    delete_event(
        event_id
    )


    return {
        "message": "Event deleted",
        "id": event_id,
    }
# ==========================
# Action Models
# ==========================


class ActionCreate(BaseModel):

    action_type: str
    action_value: str


class ActionUpdate(BaseModel):

    action_type: str
    action_value: str


class ConfigurationImport(BaseModel):

    application: str | None = None
    version: str | None = None
    preset_type: str | None = None
    action_presets: list[dict] = Field(
        default_factory=list
    )
    event_triggers: list[dict] = Field(
        default_factory=list
    )
    events: list[dict] = Field(
        default_factory=list
    )
    settings: list[dict] = Field(
        default_factory=list
    )


# ==========================
# Action API
# ==========================


@router.get("/events/{event_id}/actions")
def list_actions(
    event_id: int,
):

    return {
        "actions": get_event_actions(
            event_id
        )
    }


@router.post("/events/{event_id}/actions")
def create_action(
    event_id: int,
    action: ActionCreate,
    request: Request,
):

    require_authenticated(
        request,
        "Please login to create actions.",
    )

    add_event_action(
        event_id,
        action.action_type,
        action.action_value,
    )


    return {
        "message": "Action created",
        "event_id": event_id,
    }


@router.put("/actions/{action_id}")
def edit_action(
    action_id: int,
    action: ActionUpdate,
):

    update_event_action(
        action_id,
        action.action_type,
        action.action_value,
    )


    return {
        "message": "Action updated",
        "action_id": action_id,
    }


@router.delete("/actions/{action_id}")
def remove_action(
    action_id: int,
):

    delete_event_action(
        action_id
    )


    return {
        "message": "Action deleted",
        "action_id": action_id,
    }
    
@router.get("/export")
def export_config():

    return export_configuration()


@router.post("/import")
def import_config(
    config: ConfigurationImport,
    request: Request,
):

    if hasattr(
        config,
        "model_dump",
    ):

        payload = config.model_dump(
            exclude_unset=True
        )

    else:

        payload = config.dict(
            exclude_unset=True
        )

    imports_protected_data = any(
        key in payload
        for key in (
            "action_presets",
            "event_triggers",
            "events",
        )
    )

    try:

        with subscription_write_lock:

            if imports_protected_data:

                enforce_import_limits(
                    request,
                    (
                        len(
                            payload.get(
                                "action_presets",
                                [],
                            )
                        )
                        if "action_presets"
                        in payload
                        else None
                    ),
                    (
                        len(
                            payload.get(
                                "event_triggers",
                                [],
                            )
                        )
                        if "event_triggers"
                        in payload
                        else (
                            len(
                                payload.get(
                                    "events",
                                    [],
                                )
                            )
                            if "events"
                            in payload
                            else None
                        )
                    ),
                )

            result = import_configuration(
                payload
            )

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    return {
        "message": "Configuration imported",
        **result,
    }
