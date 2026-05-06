from ai_memory.cli.main import run as cli_run
from ai_memory.core.config import init_home
from ai_memory.store.sqlite import SQLiteMemoryStore
from ai_memory.system.init import SYSTEM_MEMORIES, seed_system_memories


def test_seed_system_memories_creates_all_records(tmp_path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()

    seeded, skipped = seed_system_memories(store)

    assert seeded == len(SYSTEM_MEMORIES)
    assert skipped == 0
    records = store.list_all(status_filter=("approved",))
    assert len(records) >= len(SYSTEM_MEMORIES)


def test_seed_system_memories_skips_existing(tmp_path):
    home = tmp_path / ".ai-memory"
    config = init_home(home)
    store = SQLiteMemoryStore(config.store_path)
    store.initialize()

    first_seeded, first_skipped = seed_system_memories(store)
    second_seeded, second_skipped = seed_system_memories(store)

    assert first_seeded == len(SYSTEM_MEMORIES)
    assert first_skipped == 0
    assert second_seeded == 0
    assert second_skipped == len(SYSTEM_MEMORIES)


def test_cli_system_init_seeds_and_reports(tmp_path, capsys):
    home = tmp_path / ".ai-memory"
    cli_run(["init", "--home", str(home)])
    result = cli_run(["system", "init", "--home", str(home)])

    assert result == 0
    output = capsys.readouterr().out
    assert "System memory seeded" in output
    assert "new" in output


def test_cli_system_init_reports_existing_on_re_run(tmp_path, capsys):
    home = tmp_path / ".ai-memory"
    cli_run(["init", "--home", str(home)])
    cli_run(["system", "init", "--home", str(home)])
    result = cli_run(["system", "init", "--home", str(home)])

    assert result == 0
    output = capsys.readouterr().out
    assert "System memory seeded" in output
    assert "existing" in output