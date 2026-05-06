from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from hashlib import sha1, sha256

from ai_memory.privacy.redactor import redact_secrets
from pathlib import Path
from typing import Any

MAX_CANDIDATES = 20
MAX_CONTENT_CHARS = 420
MIN_CONTENT_CHARS = 12
DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_TIMEOUT_SECONDS = 60
DEFAULT_LLM_MAX_INPUT_CHARS = 12000
DEFAULT_LLM_PREFILTER = True
DEFAULT_LLM_CACHE = True
DEFAULT_LLM_ONLY_IF_HEURISTIC_EMPTY = True
DEFAULT_CONFIG_PATH = Path.home() / ".ai-memory" / "extractor.json"
DEFAULT_CACHE_DIR = Path.home() / ".ai-memory" / "extractor-cache"

ALLOWED_TYPES = {
    "user_preference",
    "workflow_rule",
    "project_overview",
    "project_command",
    "coding_style",
    "testing_rule",
    "architecture_decision",
    "api_contract",
    "security_constraint",
    "pitfall",
    "bug_pattern",
    "dependency_note",
    "branch_state",
    "task_todo",
    "tool_note",
    "external_reference",
}

HIGH_IMPACT_TYPES = {
    "user_preference",
    "workflow_rule",
    "architecture_decision",
    "api_contract",
    "security_constraint",
    "coding_style",
    "testing_rule",
}

COMMAND_PATTERNS = (
    re.compile(r"\b(?:use|run|execute)\s+([A-Za-z0-9_.:/\\-]+(?:\s+[A-Za-z0-9_.:/\\-]+){0,5})\s+(?:for|to)\s+(.+)", re.I),
    re.compile(r"\b(?:test|tests|testing)\b.*\b(?:use|run|command)\b[:：]?\s*`?([^`\n。；;]{3,120})`?", re.I),
)

PREFERENCE_PATTERNS = (
    re.compile(r"\b(?:prefer|always|don't|do not|avoid|never|should)\b.+", re.I),
    re.compile(r"(?:偏好|总是|不要|避免|必须|应该|使用).+"),
)

PITFALL_PATTERNS = (
    re.compile(r"\b(?:remember|note|pitfall|gotcha|bug|fails?|failed|error|issue)\b.+", re.I),
    re.compile(r"(?:注意|坑|报错|失败|问题|修复|记住).+"),
)

SECRET_MARKERS = (
    "[REDACTED:",
    "api_key",
    "apikey",
    "password",
    "passwd",
    "authorization: bearer",
    "private key",
    "secret=",
    "token=",
)


def main() -> int:
    try:
        transcript = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("[]")
        return 0

    candidates = extract_candidates(transcript)
    print(json.dumps(candidates, ensure_ascii=False))
    return 0


def extract_candidates(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    settings = load_settings()
    mode = setting_value(settings, "mode", "AI_MEMORY_EXTRACTOR_MODE", "heuristic").strip().lower()
    if mode not in {"auto", "llm", "heuristic"}:
        mode = "heuristic"

    heuristic_candidates = extract_with_heuristics(transcript)
    if mode == "auto" and heuristic_candidates and bool_setting(
        settings,
        "llm_only_if_heuristic_empty",
        "AI_MEMORY_LLM_ONLY_IF_HEURISTIC_EMPTY",
        DEFAULT_LLM_ONLY_IF_HEURISTIC_EMPTY,
    ):
        return heuristic_candidates
    if mode in {"auto", "llm"}:
        if should_skip_llm(transcript, heuristic_candidates, settings):
            return heuristic_candidates
        llm_candidates = extract_with_llm(transcript, settings)
        if llm_candidates:
            return llm_candidates[:MAX_CANDIDATES]
        if mode == "llm":
            print("LLM extraction unavailable or returned no valid candidates; falling back to heuristic extraction.", file=sys.stderr)

    return heuristic_candidates


def should_skip_llm(transcript: dict[str, Any], heuristic_candidates: list[dict[str, Any]], settings: dict[str, Any]) -> bool:
    if not bool_setting(settings, "prefilter", "AI_MEMORY_LLM_PREFILTER", DEFAULT_LLM_PREFILTER):
        return False
    if heuristic_candidates:
        return False
    text = transcript_plain_text(transcript).casefold()
    if not text.strip():
        return True
    keywords = (
        "use ",
        "run ",
        "test",
        "command",
        "prefer",
        "always",
        "never",
        "avoid",
        "remember",
        "pitfall",
        "bug",
        "error",
        "fail",
        "注意",
        "使用",
        "不要",
        "避免",
        "必须",
        "应该",
        "测试",
        "命令",
        "报错",
        "失败",
        "坑",
    )
    return not any(keyword in text for keyword in keywords)


def load_settings() -> dict[str, Any]:
    config_path = Path(os.environ.get("AI_MEMORY_EXTRACTOR_CONFIG", str(DEFAULT_CONFIG_PATH))).expanduser()
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read extractor config {config_path}: {exc}", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print(f"Extractor config {config_path} must contain a JSON object.", file=sys.stderr)
        return {}
    return data


def setting_value(settings: dict[str, Any], key: str, env_name: str, default: str) -> str:
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return env_value
    value = settings.get(key)
    if value is None:
        return default
    return str(value)


def bool_setting(settings: dict[str, Any], key: str, env_name: str, default: bool) -> bool:
    value = os.environ.get(env_name, settings.get(key, default))
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def int_setting(settings: dict[str, Any], key: str, env_name: str, default: int) -> int:
    try:
        return int(setting_value(settings, key, env_name, str(default)))
    except ValueError:
        return default


def extract_with_llm(transcript: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    api_key = setting_value(settings, "api_key", "AI_MEMORY_LLM_API_KEY", "").strip()
    model = setting_value(settings, "model", "AI_MEMORY_LLM_MODEL", "").strip()
    if not api_key or not model:
        return []

    prompt = build_llm_prompt(transcript, settings)
    cached = read_llm_cache(transcript, prompt, settings)
    if cached is not None:
        return cached
    try:
        response_text = call_openai_compatible_chat(
            api_key=api_key,
            model=model,
            base_url=setting_value(settings, "base_url", "AI_MEMORY_LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip()
            or DEFAULT_LLM_BASE_URL,
            prompt=prompt,
            timeout_seconds=float(
                setting_value(
                    settings,
                    "timeout_seconds",
                    "AI_MEMORY_LLM_TIMEOUT_SECONDS",
                    str(DEFAULT_LLM_TIMEOUT_SECONDS),
                )
            ),
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"LLM extraction failed: {exc}", file=sys.stderr)
        return []

    try:
        raw_candidates = parse_json_array(response_text)
    except ValueError as exc:
        print(f"LLM extraction returned invalid JSON: {exc}", file=sys.stderr)
        return []

    candidates = normalize_llm_candidates(raw_candidates, transcript)
    write_llm_cache(transcript, prompt, candidates, settings)
    return candidates


def build_llm_prompt(transcript: dict[str, Any], settings: dict[str, Any]) -> str:
    text = redact_secrets(transcript_plain_text(transcript))
    max_input_chars = int_setting(settings, "max_input_chars", "AI_MEMORY_LLM_MAX_INPUT_CHARS", DEFAULT_LLM_MAX_INPUT_CHARS)
    if len(text) > max_input_chars:
        text = text[:max_input_chars] + "\n[TRUNCATED]"
    metadata = {"client": transcript.get("client")}
    return (
        "Extract durable AI coding memories from the transcript. "
        "Return ONLY a JSON array, no markdown and no prose. "
        "Each item must be an object with: type, content, summary, confidence, risk, evidence, tags, triggers. "
        "Allowed types: user_preference, workflow_rule, project_overview, project_command, coding_style, "
        "testing_rule, architecture_decision, api_contract, security_constraint, pitfall, bug_pattern, "
        "dependency_note, branch_state, task_todo, tool_note, external_reference. "
        "Use risk low, medium, or high. Confidence must be 0..1. "
        "Only extract stable, reusable facts: commands, conventions, architecture decisions, pitfalls, APIs, tests, "
        "dependencies, user preferences, and workflow rules. "
        "Do NOT extract secrets, credentials, temporary mistakes, one-off chatter, or uncertain claims. "
        "Prefer 0-10 high quality memories over many weak memories.\n\n"
        f"Metadata:\n{json.dumps(metadata, ensure_ascii=False)}\n\n"
        f"Transcript:\n{text}"
    )


def cache_key(transcript: dict[str, Any], prompt: str, settings: dict[str, Any]) -> str:
    source_path = str(transcript.get("source_path") or "")
    session_id = str(transcript.get("session_id") or "")
    model = setting_value(settings, "model", "AI_MEMORY_LLM_MODEL", "")
    payload = json.dumps(
        {
            "source_path": source_path,
            "session_id": session_id,
            "model": model,
            "prompt_sha": sha256(prompt.encode("utf-8")).hexdigest(),
        },
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def cache_dir(settings: dict[str, Any]) -> Path:
    path = setting_value(settings, "cache_dir", "AI_MEMORY_LLM_CACHE_DIR", str(DEFAULT_CACHE_DIR))
    return Path(path).expanduser()


def read_llm_cache(transcript: dict[str, Any], prompt: str, settings: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not bool_setting(settings, "cache", "AI_MEMORY_LLM_CACHE", DEFAULT_LLM_CACHE):
        return None
    path = cache_dir(settings) / f"{cache_key(transcript, prompt, settings)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    return [item for item in data if isinstance(item, dict)]


def write_llm_cache(transcript: dict[str, Any], prompt: str, candidates: list[dict[str, Any]], settings: dict[str, Any]) -> None:
    if not candidates or not bool_setting(settings, "cache", "AI_MEMORY_LLM_CACHE", DEFAULT_LLM_CACHE):
        return
    directory = cache_dir(settings)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{cache_key(transcript, prompt, settings)}.json"
        path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"Could not write LLM extraction cache: {exc}", file=sys.stderr)


def call_openai_compatible_chat(*, api_key: str, model: str, base_url: str, prompt: str, timeout_seconds: float) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You extract structured long-term coding memories. Output only valid JSON arrays.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = json.loads(response.read().decode("utf-8"))
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("missing message content")
    return content


def parse_json_array(text: str) -> list[Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if not match:
            raise ValueError("no JSON array found") from None
        data = json.loads(match.group(0))
    if not isinstance(data, list):
        raise ValueError("top-level value is not an array")
    return data


def normalize_llm_candidates(raw_candidates: list[Any], transcript: dict[str, Any]) -> list[dict[str, Any]]:
    client = str(transcript.get("client") or "generic")
    repo_id = clean_repo_id(transcript.get("repo_id"))
    branch = transcript.get("branch") if isinstance(transcript.get("branch"), str) else None
    source_path = transcript.get("source_path") if isinstance(transcript.get("source_path"), str) else ""
    session_id = transcript.get("session_id") if isinstance(transcript.get("session_id"), str) else None

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        memory_type = str(item.get("type") or "tool_note")
        if memory_type not in ALLOWED_TYPES:
            memory_type = "tool_note"
        content = normalize_content(str(item.get("content") or ""))
        if len(content) < MIN_CONTENT_CHARS or looks_sensitive(content):
            continue
        key = (memory_type, content.casefold())
        if key in seen:
            continue
        seen.add(key)
        summary = normalize_content(str(item.get("summary") or summarize(content)))
        evidence = normalize_content(str(item.get("evidence") or evidence_for(source_path, content)))
        if looks_sensitive(summary) or looks_sensitive(evidence):
            continue
        candidate = build_candidate(
            memory_type=memory_type,
            content=content,
            client=client,
            repo_id=repo_id,
            branch=branch,
            source_path=source_path,
            session_id=session_id,
        )
        candidate["summary"] = summary or summarize(content)
        candidate["confidence"] = clamp_float(item.get("confidence"), default=confidence_for(memory_type))
        candidate["risk"] = normalize_risk(item.get("risk"), memory_type)
        candidate["evidence"] = evidence or evidence_for(source_path, content)
        candidate["tags"] = clean_string_list(item.get("tags"), fallback=[client, memory_type])
        candidate["triggers"] = clean_string_list(item.get("triggers"), fallback=trigger_words(content))
        results.append(candidate)
        if len(results) >= MAX_CANDIDATES:
            break
    return results


def extract_with_heuristics(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    client = str(transcript.get("client") or "generic")
    repo_id = clean_repo_id(transcript.get("repo_id"))
    branch = transcript.get("branch") if isinstance(transcript.get("branch"), str) else None
    source_path = transcript.get("source_path") if isinstance(transcript.get("source_path"), str) else ""
    session_id = transcript.get("session_id") if isinstance(transcript.get("session_id"), str) else None

    seen: set[tuple[str, str]] = set()
    candidates: list[dict[str, Any]] = []
    for sentence in iter_sentences(transcript):
        content_type = classify_sentence(sentence)
        if content_type is None or looks_sensitive(sentence):
            continue
        content = normalize_content(sentence)
        if len(content) < MIN_CONTENT_CHARS:
            continue
        key = (content_type, content.casefold())
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            build_candidate(
                memory_type=content_type,
                content=content,
                client=client,
                repo_id=repo_id,
                branch=branch,
                source_path=source_path,
                session_id=session_id,
            )
        )
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates


def transcript_plain_text(transcript: dict[str, Any]) -> str:
    lines: list[str] = []
    messages = transcript.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "message")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def iter_sentences(transcript: dict[str, Any]) -> Iterable[str]:
    messages = transcript.get("messages")
    if not isinstance(messages, list):
        return
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")
        if role not in {"user", "assistant", "system", "transcript"}:
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        for line in split_text(content):
            yield line


def split_text(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip(" -\t\r\n")
        if not line:
            continue
        parts = re.split(r"(?<=[。！？.!?])\s+", line)
        lines.extend(part.strip() for part in parts if part.strip())
    return lines


def classify_sentence(sentence: str) -> str | None:
    if any(pattern.search(sentence) for pattern in COMMAND_PATTERNS):
        return "project_command"
    if any(pattern.search(sentence) for pattern in PREFERENCE_PATTERNS):
        return "workflow_rule"
    if any(pattern.search(sentence) for pattern in PITFALL_PATTERNS):
        return "pitfall"
    return None


def normalize_content(sentence: str) -> str:
    content = re.sub(r"\s+", " ", sentence).strip()
    if len(content) <= MAX_CONTENT_CHARS:
        return content
    return content[: MAX_CONTENT_CHARS - 1].rstrip() + "…"


def looks_sensitive(sentence: str) -> bool:
    lowered = sentence.casefold()
    return any(marker in lowered for marker in SECRET_MARKERS)


def build_candidate(
    *,
    memory_type: str,
    content: str,
    client: str,
    repo_id: str,
    branch: str | None,
    source_path: str,
    session_id: str | None,
) -> dict[str, Any]:
    uri = memory_uri(memory_type, repo_id, branch, content)
    tags = sorted({client, memory_type})
    triggers = trigger_words(content)
    return {
        "uri": uri,
        "type": memory_type,
        "scope": uri.split(":", 1)[0],
        "content": content,
        "summary": summarize(content),
        "confidence": confidence_for(memory_type),
        "risk": risk_for(memory_type),
        "evidence": evidence_for(source_path, content),
        "tags": tags,
        "triggers": triggers,
        "repo_id": None if repo_id == "local" else repo_id,
        "branch": branch,
        "source_client": client,
        "session_id": sha1(session_id.encode("utf-8")).hexdigest()[:16] if session_id else None,
        "transcript_ref": Path(source_path).name if source_path else None,
    }


def memory_uri(memory_type: str, repo_id: str, branch: str | None, content: str) -> str:
    digest = sha1(content.encode("utf-8")).hexdigest()[:10]
    slug = memory_type.replace("_", "-")
    if branch:
        return f"branch://{repo_id}/{safe_part(branch)}/{slug}-{digest}"
    return f"project://{repo_id}/{slug}-{digest}"


def clean_repo_id(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return safe_authority(value.strip())
    return "local"


def safe_authority(value: str) -> str:
    value = value.replace("\\", "/")
    value = re.sub(r"[^A-Za-z0-9._~:/-]+", "-", value)
    value = value.strip("/-")
    return value or "local"


def safe_part(value: str) -> str:
    value = value.replace("\\", "/")
    value = re.sub(r"[^A-Za-z0-9._~-]+", "-", value)
    value = value.strip("-")
    return value or "default"


def trigger_words(content: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", content.casefold())
    stop = {"the", "and", "for", "with", "that", "this", "should", "always", "never", "use", "run"}
    result: list[str] = []
    for word in words:
        if word in stop or word in result:
            continue
        result.append(word)
        if len(result) >= 6:
            break
    return result or ["history"]


def clean_string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = normalize_content(item)
        if cleaned and not looks_sensitive(cleaned) and cleaned not in result:
            result.append(cleaned)
        if len(result) >= 8:
            break
    return result or fallback


def summarize(content: str) -> str:
    if len(content) <= 96:
        return content
    return content[:95].rstrip() + "…"


def confidence_for(memory_type: str) -> float:
    if memory_type == "project_command":
        return 0.86
    if memory_type == "pitfall":
        return 0.82
    if memory_type in HIGH_IMPACT_TYPES:
        return 0.76
    return 0.72


def risk_for(memory_type: str) -> str:
    if memory_type in HIGH_IMPACT_TYPES:
        return "medium"
    return "low"


def normalize_risk(value: Any, memory_type: str) -> str:
    risk = str(value or "").strip().lower()
    if risk in {"low", "medium", "high"}:
        return risk
    return risk_for(memory_type)


def clamp_float(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, number))


def evidence_for(source_path: str, content: str) -> str:
    source = Path(source_path).name if source_path else "historical transcript"
    return summarize(f"Extracted from {source}: {content}")


if __name__ == "__main__":
    raise SystemExit(main())
