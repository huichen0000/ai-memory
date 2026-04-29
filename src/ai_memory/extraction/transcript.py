from __future__ import annotations

from ai_memory.core.models import NormalizedTranscript


def transcript_text(transcript: NormalizedTranscript) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in transcript.messages)
