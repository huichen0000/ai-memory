from pathlib import Path
import json

import yaml

from ai_memory.core.config import default_config, init_home, load_config
from ai_memory.cli.main import run


def test_default_config_uses_home_directory(tmp_path: Path):
    config = default_config(tmp_path)

    assert config.home == tmp_path / ".ai-memory"
    assert config.store_path == tmp_path / ".ai-memory" / "memory.db"
    assert config.raw_dir == tmp_path / ".ai-memory" / "raw"
    assert config.log_dir == tmp_path / ".ai-memory" / "logs"
    assert config.review_queue_path == tmp_path / ".ai-memory" / "review-queue.jsonl"
    assert config.extractor_provider == "command"
    assert config.extractor_command is not None
    assert "extractor.py" in " ".join(config.extractor_command)


def test_init_home_creates_expected_files(tmp_path: Path):
    config = init_home(tmp_path)

    assert config.home.is_dir()
    assert config.raw_dir.is_dir()
    assert config.log_dir.is_dir()
    assert config.review_queue_path.exists()
    assert config.review_queue_path.read_text(encoding="utf-8") == ""
    assert (config.home / "config.yaml").exists()
    assert (config.home / "extractor.json").exists()
    config_data = yaml.safe_load((config.home / "config.yaml").read_text(encoding="utf-8"))
    assert config_data["extractor"]["provider"] == "command"
    assert "extractor.py" in " ".join(config_data["extractor"]["command"])
    extractor_data = json.loads((config.home / "extractor.json").read_text(encoding="utf-8"))
    assert extractor_data["mode"] == "heuristic"
    assert extractor_data["base_url"] == "https://api.openai.com/v1"
    assert extractor_data["api_key"] == ""


def test_cli_init_accepts_custom_home(tmp_path: Path, capsys):
    exit_code = run(["init", "--home", str(tmp_path / "custom-memory")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Initialized ai-memory" in captured.out
    assert (tmp_path / "custom-memory" / "config.yaml").exists()


def test_cli_init_writes_manual_ai_extractor_settings(tmp_path: Path):
    home = tmp_path / "custom-memory"

    exit_code = run([
        "init",
        "--home",
        str(home),
        "--extractor-base-url",
        "https://ai.example.com/v1",
        "--extractor-api-key",
        "test-key",
        "--extractor-model",
        "example-model",
        "--extractor-mode",
        "auto",
    ])

    config = load_config(home)
    extractor_data = json.loads((home / "extractor.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert config.extractor_provider == "command"
    assert extractor_data["base_url"] == "https://ai.example.com/v1"
    assert extractor_data["api_key"] == "test-key"
    assert extractor_data["model"] == "example-model"
    assert extractor_data["mode"] == "auto"


def test_cli_commands_do_not_overwrite_existing_extractor_settings(tmp_path: Path):
    home = tmp_path / "custom-memory"
    run([
        "init",
        "--home",
        str(home),
        "--extractor-base-url",
        "https://ai.example.com/v1",
        "--extractor-api-key",
        "test-key",
        "--extractor-model",
        "example-model",
        "--extractor-mode",
        "auto",
    ])

    exit_code = run([
        "add",
        "project://local/demo/testing",
        "Use pytest for tests.",
        "--home",
        str(home),
    ])

    extractor_data = json.loads((home / "extractor.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert extractor_data["base_url"] == "https://ai.example.com/v1"
    assert extractor_data["api_key"] == "test-key"
    assert extractor_data["model"] == "example-model"
    assert extractor_data["mode"] == "auto"
