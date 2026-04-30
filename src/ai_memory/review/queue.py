from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

from ai_memory.core.models import MemoryCandidate, new_id, utc_now_iso

ReviewStatus = Literal["pending", "approved", "rejected"]
VALID_REVIEW_STATUSES = {"pending", "approved", "rejected"}


@dataclass(frozen=True)
class ReviewItem:
    id: str
    candidate: MemoryCandidate
    reason: str
    status: ReviewStatus
    created_at: str
    reviewed_at: str | None = None


class ReviewQueue:
    def __init__(self, path: Path):
        self.path = path

    def enqueue(self, candidate: MemoryCandidate, reason: str) -> ReviewItem:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        item = ReviewItem(
            id=new_id("rev"),
            candidate=candidate,
            reason=reason,
            status="pending",
            created_at=utc_now_iso(),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._item_to_dict(item), ensure_ascii=False) + "\n")
        return item

    def list_pending(self) -> list[ReviewItem]:
        return [item for item in self._read_all() if item.status == "pending"]

    def get_pending(self, review_id: str) -> ReviewItem:
        for item in self._read_all():
            if item.id == review_id:
                if item.status != "pending":
                    raise ValueError(f"Review item is not pending: {review_id}")
                return item
        raise ValueError(f"Unknown review id: {review_id}")

    def mark(self, review_id: str, status: ReviewStatus) -> None:
        status = self._validate_status(status)
        items = []
        found = False
        for item in self._read_all():
            if item.id == review_id:
                found = True
            else:
                items.append(item)
        if not found:
            raise ValueError(f"Unknown review id: {review_id}")
        self._write_all(items)

    def _read_all(self) -> list[ReviewItem]:
        if not self.path.exists():
            return []
        items = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(self._item_from_dict(json.loads(line)))
        return items

    def _write_all(self, items: list[ReviewItem]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(json.dumps(self._item_to_dict(item), ensure_ascii=False) + "\n" for item in items)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        temp_path.replace(self.path)

    def _item_to_dict(self, item: ReviewItem) -> dict[str, object]:
        data = asdict(item)
        data["candidate"] = asdict(item.candidate)
        return data

    def _item_from_dict(self, data: dict[str, object]) -> ReviewItem:
        candidate_data = data["candidate"]
        if not isinstance(candidate_data, dict):
            raise ValueError("review candidate must be an object")
        candidate_data["tags"] = tuple(candidate_data.get("tags", ()))
        candidate_data["triggers"] = tuple(candidate_data.get("triggers", ()))
        return ReviewItem(
            id=str(data["id"]),
            candidate=MemoryCandidate(**candidate_data),
            reason=str(data["reason"]),
            status=self._validate_status(data["status"]),
            created_at=str(data["created_at"]),
            reviewed_at=data.get("reviewed_at"),
        )

    def _validate_status(self, status: object) -> ReviewStatus:
        if status not in VALID_REVIEW_STATUSES:
            raise ValueError(f"Invalid review status: {status}")
        return cast(ReviewStatus, status)
