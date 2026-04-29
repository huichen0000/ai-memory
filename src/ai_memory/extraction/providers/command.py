from __future__ import annotations

import json
import subprocess
from dataclasses import asdict

from ai_memory.core.models import MemoryCandidate, NormalizedTranscript


class CommandExtractorProvider:
    def __init__(self, command: str):
        self.command = command

    def extract(self, transcript: NormalizedTranscript) -> list[MemoryCandidate]:
        payload = json.dumps(asdict(transcript), ensure_ascii=False)
        result = subprocess.run(
            self.command,
            input=payload,
            capture_output=True,
            text=True,
            shell=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "extractor command failed")
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            raise ValueError("extractor command must return a JSON list")
        candidates = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("extractor command must return a JSON list")
            item = dict(item)
            item["tags"] = tuple(item.get("tags", ()))
            item["triggers"] = tuple(item.get("triggers", ()))
            candidates.append(MemoryCandidate(**item))
        return candidates
