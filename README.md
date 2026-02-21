# kimi-advisor

CLI tool to get a second opinion from Kimi K2.5. Designed for use with Claude Code — Claude reads code and builds context, Kimi provides external perspective.

> **Key principle:** Kimi has no access to your codebase. Include relevant context (code snippets, schemas, architecture, constraints) directly in the prompt, or attach files with `-f`.

## Quick Start

**Prerequisites:** [uv](https://docs.astral.sh/uv/), [Node.js](https://nodejs.org/) (required only for the optional [blocking hook](#optional-enforce-plan-review-with-a-blocking-hook))

```bash
# 1. Set your Moonshot API key (or add it to .env.local in the project)
export KIMI_API_KEY=sk-...

# 2. Create a wrapper script so kimi-advisor works from any directory
mkdir -p ~/bin
cat > ~/bin/kimi-advisor << 'EOF'
#!/bin/bash
uv run --script /path/to/kimi_advisor.py "$@"
EOF
chmod +x ~/bin/kimi-advisor

# Ensure ~/bin is on your PATH (add to ~/.bashrc if not already):
export PATH="$HOME/bin:$PATH"

# 3. Use it — include context AND relevant files
kimi-advisor ask "We have a Node.js API (Express, 10k req/s). Sessions are in PostgreSQL. Should we use Redis or Memcached for session cache? Team has no Redis experience."

kimi-advisor review "Review the attached implementation plan." \
  -f plan.md -f src/handlers/users.js -f infra/cdk-stack.ts

kimi-advisor decompose "Decompose the migration described in the attached plan." \
  -f plan.md -f src/auth.js -f src/middleware.js
```

## Usage

### `ask` — Question, advice, second opinion

Include the full technical context: stack, code snippets, constraints, what you've considered.

```bash
kimi-advisor ask "We're building a real-time dashboard. Current stack: React + WebSocket. Data model: [paste schema]. Should we use SSE instead of WebSocket given we only need server→client updates? Constraint: must work behind AWS ALB."
```

### `review` — Critique a plan

Include the **full detailed plan** (not a summary) AND attach relevant files via `-f`. List every step with the files to modify and specific changes. A 5-line summary gets a generic review.

```bash
# Attach the plan file + relevant source files
kimi-advisor review "Review the attached implementation plan." \
  -f plan.md -f src/handlers/users.js -f src/handlers/products.js -f infra/cdk-stack.ts

# Or inline the full plan directly
kimi-advisor review "Add caching to our Express API (PostgreSQL, Lambda).

[... full detailed plan: every step with files to create/modify,
specific changes in each, dependencies, and testing strategy]" \
  -f src/handlers/users.js -f src/handlers/products.js -f infra/cdk-stack.ts
```

### `decompose` — Break down into parallel/sequential tasks

Include context, constraints, and scope — not just a one-liner. Attach the relevant code/config files.

```bash
# Attach scope description + relevant code/config
kimi-advisor decompose "Decompose the migration described in the attached plan." \
  -f plan.md -f src/routes.js -f prisma/schema.prisma -f cdk/api-stack.ts

# Or inline the full scope directly
kimi-advisor decompose "Migrate REST API to GraphQL.

[... full context: stack, architecture, constraints (backwards compat,
team size, timeline), scope of the migration]" \
  -f src/routes.js -f prisma/schema.prisma -f cdk/api-stack.ts
```

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--show-reasoning` | Display Kimi's thinking process | `False` |
| `--max-tokens` | Output token limit | `8192` |
| `--json` | Structured JSON output | `False` |
| `-f`, `--file` | Attach file(s) as context (text) or vision input (images). Repeatable. | — |

### File Attachments

Use `-f` / `--file` to attach files directly instead of pasting content into the prompt. The option is repeatable.

```bash
# Attach a single file
kimi-advisor ask "Review this schema for potential issues" -f schema.prisma

# Attach multiple files (text + image)
kimi-advisor review "Is this migration safe?" -f migration.sql -f erd.png
```

- **Text files** (any non-image extension) are included as markdown context in the prompt.
- **Images** (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, `.tiff`) are base64-encoded and sent via the vision API.
- **Limits:** 1 MB per file, 10 MB total.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KIMI_API_KEY` | Yes | — | Moonshot API key |
| `KIMI_API_BASE` | No | `https://api.moonshot.ai/v1` | API endpoint |
| `KIMI_MODEL` | No | `kimi-k2.5` | Model name |

## Claude Code Integration

Add the following to your project's `CLAUDE.md` to let Claude Code call kimi-advisor during development:

````markdown
## Kimi Advisor

Use `kimi-advisor` to get a second opinion from Kimi K2.5 on complex tasks — architecture decisions, multi-step plans, large migrations. A second opinion is valuable when there are trade-offs to weigh, multiple valid approaches, or unfamiliar territory.

**Note**: `kimi-advisor` is a read-only operation (queries an external LLM, modifies no files). It is allowed in plan mode.

**Important:** Kimi has NO access to the codebase, files, or any context beyond what you pass in the prompt. You must include all relevant code, architecture details, constraints, and examples directly in the prompt as plain text. Never reference file paths or assume Kimi can look anything up.

**Prompt content:** For `review` and `decompose`, include the **full detailed plan** in the prompt — not a summary. List every step with the files to create/modify and the specific changes planned in each. A 5-line summary gets a generic review; implementation-level detail gets actionable feedback. If the plan is very long, attach it as a `.md` file via `-f` instead of inlining it.

### Commands

```bash
# Ask a question — include full context inline
kimi-advisor ask "We have a Node.js API serving 10k req/s with this data model: [paste schema]. Sessions are stored in PostgreSQL. Should we move session storage to Redis or Memcached? Constraints: team has no Redis experience, budget is limited."

# Review a plan — attach plan file + relevant source files
kimi-advisor review "Review the attached implementation plan." \
  -f plan.md -f src/screens/LoginScreen.tsx -f src/hooks/useAuth.ts -f cdk/auth-stack.ts

# Or inline the full plan directly
kimi-advisor review "Add Google OAuth to our React Native app (Expo 51, Cognito).

[... full detailed plan: every step with files to create/modify,
specific changes in each, dependencies, and testing strategy]" \
  -f src/screens/LoginScreen.tsx -f src/hooks/useAuth.ts -f cdk/auth-stack.ts

# Decompose a task — attach scope description + relevant code/config
kimi-advisor decompose "Migrate REST API to GraphQL.

[... full context: stack, architecture, constraints (backwards compat,
team size, timeline), scope of the migration]" \
  -f src/routes.ts -f prisma/schema.prisma -f cdk/api-stack.ts

# Files-only invocation (no prompt text needed)
kimi-advisor review -f plan.md -f src/auth.py

# Pipe via stdin (auto-detected, no "-" needed)
echo "full context here..." | kimi-advisor review

# Heredoc for prompts with special characters ($, backticks, quotes)
kimi-advisor review <<'EOF'
Plan with $variables, `backticks`, and "quotes" preserved as-is.
Single-quoted delimiter ('EOF') prevents all shell interpretation.
EOF
```

> **Note for Claude Code:** Heredocs with backticks may fail due to `bash -c`
> wrapper escaping. Use file attachments or pipe instead:
> `kimi-advisor review -f plan.md` or `cat plan.md | kimi-advisor review`

### When to use

**ask** — Architecture decisions, technology choices, trade-off analysis, unfamiliar domains. Always include: the current stack, constraints, what you've considered so far.

**review** — Validate your implementation plan before starting. Always include: the full detailed plan AND relevant files via `-f` (code, config, schemas).

**decompose** — Large migrations, multi-component features. Always include: context, constraints, scope AND relevant files via `-f` (routes, schemas, infra).

### Prompt quality checklist

Before calling kimi-advisor, verify your prompt includes:
- [ ] The actual code or schema (not just file names)
- [ ] Tech stack and framework versions
- [ ] Constraints (team skills, budget, timeline, existing infra)
- [ ] What you've already considered or tried
- [ ] The specific question or decision point
- [ ] For review/decompose: the full detailed plan (every step, files to modify, specific changes — not a summary)
````

### Optional: Enforce plan review with a blocking hook

The CLAUDE.md approach above is **advisory** — Claude should follow it, but nothing prevents it from skipping the review. For a **blocking** guarantee, use a `PreToolUse` hook on `ExitPlanMode` that checks the session transcript for actual `kimi-advisor` execution before allowing Claude to exit plan mode.

**1. Add the hook config** to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [
          {
            "type": "command",
            "command": "node .claude/hooks/pre-exit-plan-mode.mjs"
          }
        ]
      }
    ]
  }
}
```

**2. Copy the hook script** into the target project's `.claude/hooks/` directory:

```bash
# From the project where you want to enforce the hook:
mkdir -p .claude/hooks
cp /path/to/kimi-advisor/.claude/hooks/pre-exit-plan-mode.mjs .claude/hooks/
```

The script is included in this repo at [`.claude/hooks/pre-exit-plan-mode.mjs`](.claude/hooks/pre-exit-plan-mode.mjs). It requires Node.js and the [`claude` CLI](https://docs.anthropic.com/en/docs/claude-code) (used to call Haiku for transcript analysis).

**How it works:**
- When Claude calls `ExitPlanMode`, the hook intercepts the call
- It reads the session transcript and sends it to Claude Haiku for analysis
- Haiku checks whether `kimi-advisor` was actually **executed** via a Bash tool call (not just mentioned in system prompts or CLAUDE.md)
- If executed → the hook allows `ExitPlanMode` to proceed
- If not → the hook **denies** the call with a message telling Claude to run `kimi-advisor review` first
- On any error (no transcript, Haiku timeout, etc.) → the hook exits silently and falls back to normal behavior

**Advisory (CLAUDE.md) vs. Blocking (hook):**

| | CLAUDE.md | PreToolUse hook |
|---|---|---|
| Mechanism | Instruction in system prompt | Script that gates `ExitPlanMode` |
| Enforcement | Soft — Claude may skip it | Hard — Claude cannot exit plan mode |
| Dependencies | None | `claude` CLI (for Haiku call) |
| Failure mode | Claude proceeds without review | Falls back to normal (allows exit) |

### Workflow

1. Claude reads code, understands context
2. Claude formulates a plan or question, **including all relevant code and context inline**
3. Claude calls `kimi-advisor` for external perspective
4. Claude adjusts based on Kimi's feedback
5. Claude implements

> Remember: Kimi sees only what's in the prompt. Claude must paste code snippets, schemas, and architecture details — not file paths.

## Development

```bash
# Run tests (no API key needed, everything is mocked)
uv run --group test pytest -v
```

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Claude       │────▶│   kimi-advisor   │────▶│  Moonshot API   │
│ (context)   │     │   ask/review/    │     │  Kimi K2.5      │
│             │     │   decompose      │     │  (thinking on)  │
└─────────────┘     └──────────────────┘     └─────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  stdout (markdown)│
                    └──────────────────┘
```

## License

MIT
