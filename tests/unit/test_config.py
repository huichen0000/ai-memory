from pathlib import Path

from ai_memory.core.config import AppConfig, default_config, init_home
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
