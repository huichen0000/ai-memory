from pathlib import Path

import yaml

from ai_memory.core.config import AppConfig, default_config, init_home, load_config
from ai_memory.cli.main import run


def test_default_config_uses_home_directory(tmp_path: Path):
    config = default_config(tmp_path)

    assert config.home == tmp_path / ".ai-memory"
    assert config.store_path == tmp_path / ".ai-memory" / "memory.db"
    assert config.raw_dir == tmp_path / ".ai-memory" / "raw"
    assert config.log_dir == tmp_path / ".ai-memory" / "logs"
    assert config.review_queue_path == tmp_path / ".ai-memory" / "review-queue.jsonl"
    assert config.extractor_provider is None


def test_init_home_creates_expected_files(tmp_path: Path):
    config = init_home(tmp_path)

    assert config.home.is_dir()
    assert config.raw_dir.is_dir()
    assert config.log_dir.is_dir()
    assert config.review_queue_path.exists()
    assert config.review_queue_path.read_text(encoding="utf-8") == ""
    assert (config.home / "config.yaml").exists()


def test_cli_init_accepts_custom_home(tmp_path: Path, capsys):
    exit_code = run(["init", "--home", str(tmp_path / "custom-memory")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Initialized ai-memory" in captured.out
    assert (tmp_path / "custom-memory" / "config.yaml").exists()


def test_cli_context_preserves_existing_config(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    data = {
        "store": {"path": str(config.store_path)},
        "paths": {
            "raw_dir": str(config.raw_dir),
            "log_dir": str(config.log_dir),
            "review_queue": str(config.review_queue_path),
        },
        "extractor": {
            "provider": "command",
            "command": ["python", "D:/tools/extractor.py"],
            "max_input_chars": 60000,
        },
    }
    config_file = home / "config.yaml"
    config_file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    assert run(["context", "--home", str(home), "--prompt", "pytest"]) == 0

    loaded = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert loaded["extractor"]["provider"] == "command"
    assert loaded["extractor"]["command"] == ["python", "D:/tools/extractor.py"]


def test_load_config_accepts_list_extractor_command(tmp_path: Path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    data = {
        "store": {"path": str(config.store_path)},
        "paths": {
            "raw_dir": str(config.raw_dir),
            "log_dir": str(config.log_dir),
            "review_queue": str(config.review_queue_path),
        },
        "extractor": {
            "provider": "command",
            "command": ["python", "D:/tools/extractor.py"],
            "max_input_chars": 60000,
        },
    }
    (home / "config.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    loaded = load_config(home)

    assert loaded.extractor_provider == "command"
    assert loaded.extractor_command == ["python", "D:/tools/extractor.py"]
