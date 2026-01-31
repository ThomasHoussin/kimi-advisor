## Development Guide

Single-file Python CLI tool (`kimi_advisor.py`) that queries Kimi K2.5 via the Moonshot API. Runs as a [uv script](https://docs.astral.sh/uv/guides/scripts/) with PEP 723 inline metadata — no install step, `uv` resolves dependencies automatically.

### Tech Stack

- Python 3.11+, uv (script mode)
- `click` — CLI framework
- `openai` — API client (Moonshot API is OpenAI-compatible)
- `python-dotenv` — loads `.env.local` / `.env`
- `pytest` — tests (dev dependency)
- `ruff` — formatting (run via `uvx`)

### Project Structure

```
kimi_advisor.py          # Entry point — uv script with inline deps
prompts/
  ask.md                 # System prompt for "ask" command
  review.md              # System prompt for "review" command
  decompose.md           # System prompt for "decompose" command
tests/
  test_kimi_advisor.py   # Full test suite (all mocked, no API calls)
pyproject.toml           # Project metadata + pytest config + test deps
```

### Setup

```bash
# Add your Moonshot API key to .env.local (gitignored)
echo "KIMI_API_KEY=sk-..." > .env.local
```

No other setup needed — `uv` handles the virtual environment and dependencies.

### Commands

```bash
# Run locally
uv run kimi_advisor.py ask "your question"
uv run kimi_advisor.py review "your plan"
uv run kimi_advisor.py decompose "your task"

# Run tests (no API key needed)
uv run --group test pytest -v

# Format code
uvx ruff format .
```

### Architecture

- **`KimiClient`** — wraps the OpenAI client pointed at Moonshot API. Handles auth, retry with exponential backoff (up to 3 attempts on 429/5xx), and response parsing (extracts `reasoning_content` + `content`).
- **System prompts** — loaded from `prompts/*.md` at module init. Each command (`ask`, `review`, `decompose`) has its own prompt defining Kimi's role and output format.
- **File attachments** — `--file` / `-f` option (repeatable) on all commands. Auto-detects text vs image by extension. Text files are included as markdown context, images are base64-encoded and sent via OpenAI vision format. Limits: 1 MB per file, 10 MB total. The tool reads any file the user has OS-level permission to access — this is by design, as the purpose is to send file contents to the API for analysis.
- **CLI layer** — Click group with 3 commands sharing common options (`--show-reasoning`, `--max-tokens`, `--json`, `--file`). Supports stdin via `-` argument.
- **Output** — markdown by default, structured JSON with `--json`. Reasoning displayed only with `--show-reasoning`.

### Conventions

- All errors raised as `click.ClickException` (user-friendly messages, no tracebacks)
- All file paths relative to `SCRIPT_DIR` (`Path(__file__).resolve().parent`) — works from any working directory
- System prompts are plain markdown files — edit `prompts/*.md` to change Kimi's behavior
- Tests mock the OpenAI client at the class level — never hit the real API
- Environment variables: `KIMI_API_KEY` (required), `KIMI_API_BASE` and `KIMI_MODEL` (optional overrides)

### Commit Message Convention
This project follows the [Conventional Commits](https://www.conventionalcommits.org/) specification.

**Format**: `<type>(<scope>): <description>`

**Types** (semantic versioning impact):
| Type | Description | Version Impact |
|------|-------------|----------------|
| `feat` | New feature | Minor (0.x.0) |
| `fix` | Bug fix | Patch (0.0.x) |
| `feat!` / `BREAKING CHANGE:` | Breaking change | Major (x.0.0) |
| `docs` | Documentation only | None |
| `style` | Code style/formatting | None |
| `refactor` | Code restructuring | None |
| `perf` | Performance improvement | None |
| `test` | Adding/updating tests | None |
| `build` | Build system/dependencies | None |
| `ci` | CI configuration | None |
| `chore` | Maintenance | None |

**Examples**:
```
feat(auth): add OAuth2 login support
fix(api): resolve timeout on large uploads
docs: update installation guide
refactor(mobile): extract common form components
feat!: redesign user profile API
```