# AI Agent Instructions

- Keep changes small and directly tied to the current task.
- Prefer the Python standard library unless a dependency is already in `pyproject.toml`.
- Use tests before implementation for behavior changes.
- Do not store secrets, tokens, private keys, or `.env` values in fixtures.
- Run the most specific pytest target before marking a task complete.
