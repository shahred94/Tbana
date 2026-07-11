"""Chat TTS configuration and queue controls."""

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from app.tts.chat import chat_tts_service, load_config, save_config


router = APIRouter(prefix="/api/chat-tts", tags=["Chat TTS"])


class ChatTTSUpdate(BaseModel):
    config: dict


@router.get("")
def get_chat_tts():
    return {"config": asdict(load_config()), "queue": chat_tts_service.status()}


@router.get("/status")
def get_chat_tts_status():
    return {"queue": chat_tts_service.status()}


@router.put("")
def update_chat_tts(update: ChatTTSUpdate):
    return {"config": asdict(save_config(update.config)), "queue": chat_tts_service.status()}


@router.post("/test")
def test_chat_tts():
    accepted = chat_tts_service.submit(
        nickname="TBana Viewer", username="tbana_viewer",
        comment="Ini ujian TTS Chat.", metadata={"viewer_type": "follower"},
    )
    return {"accepted": accepted, "queue": chat_tts_service.status()}


@router.post("/skip")
def skip_chat_tts():
    return {"skipped": chat_tts_service.skip(), "queue": chat_tts_service.status()}


@router.delete("/queue")
def clear_chat_tts_queue():
    return {"cleared": chat_tts_service.clear(), "queue": chat_tts_service.status()}
