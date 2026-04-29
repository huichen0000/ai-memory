from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import asdict
from typing import Sequence

from ai_memory.core.models import MemoryCandidate, NormalizedTranscript

REQUIRED_CANDIDATE_FIELDS = {"uri", "type", "scope", "content", "summary", "confidence", "risk", "evidence"}


class CommandExtractorProvider:
    def __init__(self, command: str | Sequence[str], timeout_seconds: float = 30):
        self.command = shlex.split(command) if isinstance(command, str) else list(command)
        self.timeout_seconds = timeout_seconds

    def extract(self, transcript: NormalizedTranscript) -> list[MemoryCandidate]:
        payload = json.dumps(asdict(transcript), ensure_ascii=False)
        try:
            result = subprocess.run(
                self.command,
                input=payload,
                capture_output=True,
                text=True,
                shell=False,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("extractor command timed out") from exc
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "extractor command failed")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("extractor command returned invalid JSON") from exc
        if not isinstance(data, list):
            raise ValueError("extractor command must return a JSON list")
        candidates = []
        for item in data:
            candidates.append(self._candidate_from_item(item))
        return candidates

    def _candidate_from_item(self, item: object) -> MemoryCandidate:
        if not isinstance(item, dict):
            raise ValueError("extractor command candidate output must be an object")
        missing_fields = REQUIRED_CANDIDATE_FIELDS - item.keys()
        if missing_fields:
            raise ValueError("extractor command candidate output missing required field")
        candidate_data = dict(item)
        for field in ("tags", "triggers"):
            values = candidate_data.get(field, ())
            if not isinstance(values, (list, tuple)):
                raise ValueError(f"extractor command candidate {field} must be a list or tuple")
            candidate_data[field] = tuple(values)
        try:
            return MemoryCandidate(**candidate_data)
        except TypeError as exc:
            raise ValueError("extractor command returned invalid candidate output") from exc
