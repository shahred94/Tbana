import html
import re
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

import edge_tts
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.auth.service import (
    enforce_action_creation,
    enforce_trigger_creation,
    require_feature,
    subscription_write_lock,
)
from app.storage.sqlite_store import (
    get_action_presets,
    create_action_preset,
    delete_action_preset,

    get_action_steps,
    add_action_step,
    delete_action_step,

    get_event_triggers,
    create_event_trigger,
    update_event_trigger,
    update_event_trigger_status,
    update_action_preset,
    update_action_preset_status,
    delete_event_trigger,
)

from app.actions.executor import (
    action_executor,
)
from app.api.test_timing import normalize_test_delay

router = APIRouter(
    prefix="/api/actions",
    tags=[
        "Actions V2"
    ],
)

tts_voice_cache = []

fallback_tts_voices = [
    {
        "name": "ms-MY-YasminNeural",
        "locale": "ms-MY",
        "gender": "Female",
        "display_name": "Yasmin (Malay, Malaysia)",
    },
    {
        "name": "ms-MY-OsmanNeural",
        "locale": "ms-MY",
        "gender": "Male",
        "display_name": "Osman (Malay, Malaysia)",
    },
    {
        "name": "en-MY-YasminNeural",
        "locale": "en-MY",
        "gender": "Female",
        "display_name": "Yasmin (English, Malaysia)",
    },
    {
        "name": "en-MY-OsmanNeural",
        "locale": "en-MY",
        "gender": "Male",
        "display_name": "Osman (English, Malaysia)",
    },
    {
        "name": "en-US-JennyNeural",
        "locale": "en-US",
        "gender": "Female",
        "display_name": "Jenny (English, United States)",
    },
    {
        "name": "en-US-GuyNeural",
        "locale": "en-US",
        "gender": "Male",
        "display_name": "Guy (English, United States)",
    },
]


class ActionCreate(BaseModel):

    name: str

    duration: int = 0

    description: str = ""

    media_volume: int = 100

    overlay_screen: int = 1

    global_cooldown: int = 0

    user_cooldown: int = 0

    fade_enabled: bool = False

    repeat_gift_combos: bool = False

    skip_on_next_action: bool = False


class ActionStepCreate(BaseModel):

    order: int = 0

    type: str

    value: str


class MyinstantsImportRequest(BaseModel):

    name: str

    media_url: str
    
class EventTriggerCreate(BaseModel):

    trigger_type: str

    trigger_value: str

    user_filter: str = "ANY"

    action_id: int

    action_mode: str = "single"

    action_group: str = ""


class EventTriggerStatusUpdate(BaseModel):

    enabled: bool


class ActionStatusUpdate(BaseModel):

    enabled: bool


def copy_name(
    original_name: str,
    existing_names: list[str],
) -> str:
    """Return a readable unique name for a duplicated action."""

    taken = {
        str(name).strip().lower()
        for name in existing_names
    }
    base = f"{str(original_name).strip()} (Copy)"
    candidate = base
    number = 2

    while candidate.lower() in taken:
        candidate = f"{base} {number}"
        number += 1

    return candidate
    
@router.get("/event-triggers")
def list_event_triggers():

    return {
        "events":
        get_event_triggers()
    }


@router.post("/event-triggers")
def create_event(
    event: EventTriggerCreate,
    request: Request,
):

    with subscription_write_lock:

        enforce_trigger_creation(
            request
        )

        create_event_trigger(
            event.trigger_type,
            event.trigger_value,
            event.user_filter,
            event.action_id,
            event.action_mode,
            event.action_group,
        )

    return {
        "message":
        "Event trigger created"
    }


@router.post("/event-triggers/{trigger_id}/duplicate")
def duplicate_event_trigger(
    trigger_id: int,
    request: Request,
):

    source = next(
        (
            event
            for event in get_event_triggers()
            if event["id"] == trigger_id
        ),
        None,
    )

    if source is None:
        raise HTTPException(
            status_code=404,
            detail="Event trigger not found.",
        )

    with subscription_write_lock:

        enforce_trigger_creation(
            request
        )

        duplicate_id = create_event_trigger(
            source["trigger_type"],
            source["trigger_value"],
            source["user_filter"],
            source["action_id"],
            source["action_mode"],
            source["action_group"],
        )

        if not source["enabled"]:
            update_event_trigger_status(
                duplicate_id,
                False,
            )

    return {
        "message": "Event duplicated",
        "id": duplicate_id,
    }


@router.delete("/event-triggers/{trigger_id}")
def remove_event(
    trigger_id: int,
):

    delete_event_trigger(
        trigger_id
    )

    return {
        "message":
        "Event trigger deleted"
    }


@router.put("/event-triggers/{trigger_id}")
def edit_event_trigger(
    trigger_id: int,
    event: EventTriggerCreate,
):

    update_event_trigger(
        trigger_id,
        event.trigger_type,
        event.trigger_value,
        event.user_filter,
        event.action_id,
        event.action_mode,
        event.action_group,
    )

    return {
        "message":
        "Event trigger updated"
    }


@router.put("/event-triggers/{trigger_id}/status")
def change_event_trigger_status(
    trigger_id: int,
    status: EventTriggerStatusUpdate,
):

    update_event_trigger_status(
        trigger_id,
        status.enabled,
    )

    return {
        "message":
        "Event trigger status updated"
    }


@router.get("")
def list_actions():

    return {
        "actions":
        get_action_presets()
    }


@router.get("/sounds")
def list_sounds():

    sounds_path = Path(
        "sounds"
    )

    allowed_extensions = {
        ".mp3",
        ".wav",
        ".ogg",
    }

    sounds = []

    if sounds_path.exists():

        for file_path in sorted(
            sounds_path.iterdir()
        ):

            if (
                file_path.is_file()
                and
                file_path.suffix.lower()
                in
                allowed_extensions
            ):

                sounds.append({
                    "name": file_path.name,
                    "url": f"/sounds/{file_path.name}",
                })

    return {
        "sounds": sounds
    }

@router.get("/tts/voices")
async def list_tts_voices(
    request: Request,
    refresh: bool = False,
):

    """List Edge TTS voices, with useful offline fallback options."""

    require_feature(
        request,
        "edge_tts",
        "Edge TTS is available on the Pro plan.",
    )

    global tts_voice_cache

    if (
        tts_voice_cache
        and
        not refresh
    ):

        return {
            "voices": tts_voice_cache,
            "online": True,
        }

    try:

        voices = await edge_tts.list_voices()

        tts_voice_cache = sorted(
            [
                {
                    "name": voice.get(
                        "ShortName",
                        "",
                    ),
                    "locale": voice.get(
                        "Locale",
                        "",
                    ),
                    "gender": voice.get(
                        "Gender",
                        "",
                    ),
                    "display_name": (
                        voice.get(
                            "FriendlyName"
                        )
                        or
                        voice.get(
                            "ShortName",
                            "",
                        )
                    ),
                }
                for voice in voices
                if voice.get(
                    "ShortName"
                )
            ],
            key=lambda voice: (
                voice["locale"],
                voice["name"],
            ),
        )

        return {
            "voices": tts_voice_cache,
            "online": True,
        }

    except Exception as error:

        return {
            "voices": fallback_tts_voices,
            "online": False,
            "message": (
                "Could not download the full Edge TTS voice list. "
                f"Using common voices: {error}"
            ),
        }


def myinstants_request(
    url: str,
) -> str:

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
            "LiveTrigger/2.0",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=10,
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="ignore",
        )


def extract_myinstants_media_url(
    page_html: str,
) -> str:

    patterns = [
        r'href="(?P<url>https?://[^"]+?\.mp3[^"]*)"',
        r'href="(?P<url>/media/sounds/[^"]+?\.mp3[^"]*)"',
        r'src="(?P<url>https?://[^"]+?\.mp3[^"]*)"',
        r'src="(?P<url>/media/sounds/[^"]+?\.mp3[^"]*)"',
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            page_html,
            re.IGNORECASE,
        )

        if match:

            media_url = html.unescape(
                match.group(
                    "url"
                )
            )

            return urllib.parse.urljoin(
                "https://www.myinstants.com",
                media_url,
            )

    return ""


def safe_sound_filename(
    name: str,
) -> str:

    stem = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "_",
        name.strip(),
    ).strip(
        "._"
    )

    if not stem:

        stem = "myinstants_sound"

    if not stem.lower().endswith(
        ".mp3"
    ):

        stem += ".mp3"

    return stem[:120]


@router.get("/myinstants/search")
def search_myinstants(
    query: str = "",
    limit: int = 12,
):

    query = query.strip()

    if not query:

        return {
            "sounds": []
        }

    limit = max(
        1,
        min(
            limit,
            20,
        )
    )

    search_url = (
        "https://www.myinstants.com/en/search/?name="
        +
        urllib.parse.quote_plus(
            query
        )
    )

    try:

        page_html = myinstants_request(
            search_url
        )

    except urllib.error.URLError as error:

        return {
            "sounds": [],
            "ok": False,
            "message": str(error),
        }

    matches = re.findall(
        r'<a[^>]+href="(?P<href>/en/instant/[^"]+/)"[^>]*>(?P<title>.*?)</a>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    sounds = []
    seen = set()

    for href, title in matches:

        if href in seen:

            continue

        seen.add(
            href
        )

        page_url = urllib.parse.urljoin(
            "https://www.myinstants.com",
            href,
        )

        try:

            detail_html = myinstants_request(
                page_url
            )

        except urllib.error.URLError:

            continue

        media_url = extract_myinstants_media_url(
            detail_html
        )

        if not media_url:

            continue

        clean_title = re.sub(
            r"\s+",
            " ",
            html.unescape(
                re.sub(
                    r"<[^>]+>",
                    "",
                    title,
                )
            ),
        ).strip()

        sounds.append({
            "name": clean_title,
            "page_url": page_url,
            "media_url": media_url,
            "source": "myinstants",
        })

        if len(sounds) >= limit:

            break

    return {
        "sounds": sounds,
        "ok": True,
    }


@router.post("/myinstants/import")
def import_myinstants_sound(
    request: MyinstantsImportRequest,
):

    media_url = request.media_url.strip()

    if not media_url.startswith(
        "https://www.myinstants.com/"
    ):

        return {
            "message":
            "Only Myinstants URLs are supported.",
            "ok":
            False,
        }

    sounds_path = Path(
        "sounds"
    )

    sounds_path.mkdir(
        exist_ok=True
    )

    filename = safe_sound_filename(
        request.name
    )

    target_path = sounds_path / filename

    counter = 1

    while target_path.exists():

        filename = safe_sound_filename(
            f"{Path(request.name).stem}_{counter}.mp3"
        )

        target_path = sounds_path / filename

        counter += 1

    req = urllib.request.Request(
        media_url,
        headers={
            "User-Agent":
            "LiveTrigger/2.0",
        },
    )

    try:

        with urllib.request.urlopen(
            req,
            timeout=15,
        ) as response:

            target_path.write_bytes(
                response.read()
            )

    except urllib.error.URLError as error:

        return {
            "message": str(error),
            "ok": False,
        }

    return {
        "message":
        "Sound imported",
        "ok":
        True,
        "name":
        filename,
        "url":
        f"/sounds/{filename}",
    }


@router.post("")
def create_action(
    action: ActionCreate,
    request: Request,
):

    with subscription_write_lock:

        enforce_action_creation(
            request
        )

        action_id = create_action_preset(
            action.name,
            action.duration,
            action.description,
            action.media_volume,
            action.overlay_screen,
            action.global_cooldown,
            action.user_cooldown,
            action.fade_enabled,
            action.repeat_gift_combos,
            action.skip_on_next_action,
        )

    return {
        "message":
        "Action created",
        "id":
        action_id
    }


@router.post("/{action_id}/duplicate")
def duplicate_action(
    action_id: int,
    request: Request,
):

    actions = get_action_presets()
    source = next(
        (
            action
            for action in actions
            if action["id"] == action_id
        ),
        None,
    )

    if source is None:
        raise HTTPException(
            status_code=404,
            detail="Action not found.",
        )

    source_steps = get_action_steps(
        action_id
    )

    if any(
        step["type"].strip().lower()
        ==
        "tts"
        for step in source_steps
    ):

        require_feature(
            request,
            "edge_tts",
            "Edge TTS is available on the Pro plan.",
        )

    with subscription_write_lock:

        enforce_action_creation(
            request
        )

        duplicate_id = create_action_preset(
            copy_name(
                source["name"],
                [
                    action["name"]
                    for action in actions
                ],
            ),
            source["duration"],
            source["description"],
            source["media_volume"],
            source["overlay_screen"],
            source["global_cooldown"],
            source["user_cooldown"],
            source["fade_enabled"],
            source["repeat_gift_combos"],
            source["skip_on_next_action"],
        )

        for step in source_steps:
            add_action_step(
                duplicate_id,
                step["order"],
                step["type"],
                step["value"],
            )

        if not source["enabled"]:
            update_action_preset_status(
                duplicate_id,
                False,
            )

    return {
        "message": "Action duplicated",
        "id": duplicate_id,
    }


@router.put("/{action_id}/status")
def change_action_status(
    action_id: int,
    status: ActionStatusUpdate,
):

    update_action_preset_status(
        action_id,
        status.enabled,
    )

    return {
        "message": "Action status updated"
    }


@router.put("/{action_id}")
def update_action(
    action_id: int,
    action: ActionCreate,
):

    update_action_preset(
        action_id,
        action.name,
        action.duration,
        action.description,
        action.media_volume,
        action.overlay_screen,
        action.global_cooldown,
        action.user_cooldown,
        action.fade_enabled,
        action.repeat_gift_combos,
        action.skip_on_next_action,
    )

    return {
        "message":
        "Action updated"
    }

@router.delete("/{action_id}")
def delete_action(
    action_id: int,
):

    delete_action_preset(
        action_id
    )

    return {
        "message":
        "Action deleted"
    }

@router.post("/{action_id}/test")
def test_action(
    action_id: int,
    request: Request,
    delay_seconds: float = 0,
):

    test_delay = normalize_test_delay(
        delay_seconds
    )
    if test_delay:
        time.sleep(
            test_delay
        )

    action_preset = next(
        (
            action
            for action in get_action_presets()
            if action["id"] == action_id
        ),
        {},
    )

    steps = get_action_steps(
        action_id
    )

    if any(
        step["type"].lower()
        ==
        "tts"
        for step in steps
    ):

        require_feature(
            request,
            "edge_tts",
            "Edge TTS is available on the Pro plan.",
        )


    action_deadline = action_executor.deadline_from_action(
        {
            "max_duration": action_preset.get(
                "duration",
                0,
            )
        }
    )

    for step in steps:

        action_type = (
            step["type"]
            .lower()
        )


        action = None


        if action_type == "sound":

            action = {
                "type": "sound",
                "sound": step["value"],
                "volume": action_preset.get(
                    "media_volume",
                    100,
                ),
            }


        elif action_type == "keyboard":

            action = {
                "type": "keyboard",
                "key": step["value"],
            }


        elif action_type == "tts":

            action = {
                "type": "tts",
                "text": step["value"],
            }

        elif action_type == "webhook":

            action = {
                "type": "webhook",
                "url": step["value"],
            }


        if action:

            action[
                "max_duration"
            ] = action_preset.get(
                "duration",
                0,
            )

            action_executor.execute(
                action,
                deadline=action_deadline,
            )


    return {
        "message":
        "Action tested"
    }
    
@router.get("/{action_id}/steps")
def list_action_steps(
    action_id: int,
):

    return {
        "steps":
        get_action_steps(action_id)
    }


@router.post("/{action_id}/steps")
def create_action_step(
    action_id: int,
    step: ActionStepCreate,
    request: Request,
):

    if (
        step.type.strip().lower()
        ==
        "tts"
    ):

        require_feature(
            request,
            "edge_tts",
            "Edge TTS is available on the Pro plan.",
        )

    add_action_step(
        action_id,
        step.order,
        step.type,
        step.value,
    )

    return {
        "message":
        "Action step created"
    }


@router.delete("/steps/{step_id}")
def remove_action_step(
    step_id: int,
):

    delete_action_step(
        step_id
    )

    return {
        "message":
        "Action step deleted"
    }
