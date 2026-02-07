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

# review / decompose: provide context AND relevant files via -f
uv run kimi_advisor.py review "migrate auth from sessions to JWT" \
  -f src/auth.py -f src/middleware.py -f docs/auth-spec.md
uv run kimi_advisor.py decompose "add rate limiting to API" \
  -f src/routes.py -f src/config.py

# Run tests (no API key needed)
uv run --group test pytest -v

# Format code
uvx ruff format .
```

### Architecture

- **`KimiClient`** — wraps the OpenAI client pointed at Moonshot API. Handles auth, retry with exponential backoff (up to 3 attempts on 429/5xx), and response parsing (extracts `reasoning_content` + `content`).
- **System prompts** — loaded from `prompts/*.md` at module init. Each command (`ask`, `review`, `decompose`) has its own prompt defining Kimi's role and output format.
- **File attachments** — `--file` / `-f` option (repeatable) on all commands. Auto-detects text vs image by extension. Text files are included as markdown context, images are base64-encoded and sent via OpenAI vision format. Limits: 1 MB per file, 10 MB total. The tool reads any file the user has OS-level permission to access — this is by design, as the purpose is to send file contents to the API for analysis.
- **CLI layer** — Click group with 3 commands sharing common options (`--show-reasoning`, `--max-tokens`, `--json`, `--file`). Supports stdin via `-` argument or auto-detected when no argument is given (enables heredoc usage for prompts with special characters).
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

## Kimi Advisor

Use `kimi-advisor` to get a second opinion from Kimi K2.5 on complex tasks — architecture decisions, multi-step plans, large migrations. A second opinion is valuable when there are trade-offs to weigh, multiple valid approaches, or unfamiliar territory.

**Note**: `kimi-advisor` is a read-only operation (queries an external LLM, modifies no files). It is allowed in plan mode.

**Important:** Kimi has NO access to the codebase, files, or any context beyond what you pass in the prompt. You must include all relevant code, architecture details, constraints, and examples directly in the prompt as plain text. Never reference file paths or assume Kimi can look anything up.

### Commands

```bash
# Ask a question — include full context inline
kimi-advisor ask "We have a Node.js API serving 10k req/s with this data model: [paste schema]. Sessions are stored in PostgreSQL. Should we move session storage to Redis or Memcached? Constraints: team has no Redis experience, budget is limited."

# Review a plan — describe the plan AND attach relevant files
kimi-advisor review "Add Google OAuth to our React Native app (Expo, Cognito).
Plan:
1. Add Google OAuth provider in Cognito
2. Install expo-auth-session
3. Create useGoogleAuth hook
4. Add Google Sign-In button to LoginScreen
5. Map Google profile to existing user model" \
  -f src/screens/LoginScreen.tsx -f src/hooks/useAuth.ts -f cdk/auth-stack.ts

# Decompose a task — describe scope and attach code/config
kimi-advisor decompose "Migrate REST API to GraphQL. Must maintain backwards compat during migration." \
  -f src/routes.ts -f prisma/schema.prisma -f cdk/api-stack.ts

# Pipe via stdin (auto-detected, no "-" needed)
echo "full context here..." | kimi-advisor review

# Heredoc for prompts with special characters ($, backticks, quotes)
kimi-advisor review <<'EOF'
Plan with $variables, `backticks`, and "quotes" preserved as-is.
Single-quoted delimiter ('EOF') prevents all shell interpretation.
EOF
```

### When to use

**ask** — Architecture decisions, technology choices, trade-off analysis, unfamiliar domains. Always include: the current stack, constraints, what you've considered so far.

**review** — Validate your implementation plan before starting. Always include: the plan description AND relevant files via `-f` (code, config, schemas).

**decompose** — Large migrations, multi-component features. Always include: scope/constraints description AND relevant files via `-f` (routes, schemas, infra).

### Prompt quality checklist

Before calling kimi-advisor, verify your prompt includes:
- [ ] The actual code or schema (not just file names)
- [ ] Tech stack and framework versions
- [ ] Constraints (team skills, budget, timeline, existing infra)
- [ ] What you've already considered or tried
- [ ] The specific question or decision point