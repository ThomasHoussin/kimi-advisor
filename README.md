# kimi-advisor

CLI tool to get a second opinion from Kimi K2.5. Designed for use with Claude Code — Claude reads code and builds context, Kimi provides external perspective.

> **Key principle:** Kimi has no access to your codebase. Include relevant context (code snippets, schemas, architecture, constraints) directly in the prompt, or attach files with `-f`.

## Quick Start

**Prerequisites:** [uv](https://docs.astral.sh/uv/)

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

# 3. Use it — include full context
kimi-advisor ask "We have a Node.js API (Express, 10k req/s). Sessions are in PostgreSQL. Should we use Redis or Memcached for session cache? Team has no Redis experience."

kimi-advisor review "Context: React app with Zustand state management. Plan: 1. Add Redis client wrapper 2. Create cache decorator using this pattern: [paste code] 3. Add TTL config 4. Write tests"

kimi-advisor decompose "Migrate auth from session-based to JWT. Current stack: Express API, PostgreSQL, 15 endpoints. Current session code: [paste snippet]. Must maintain backwards compat."
```

## Usage

### `ask` — Question, advice, second opinion

Include the full technical context: stack, code snippets, constraints, what you've considered.

```bash
kimi-advisor ask "We're building a real-time dashboard. Current stack: React + WebSocket. Data model: [paste schema]. Should we use SSE instead of WebSocket given we only need server→client updates? Constraint: must work behind AWS ALB."
```

### `review` — Critique a plan

Include both the plan and the relevant code/architecture context.

```bash
kimi-advisor review "Goal: Add caching to our API.
Current code: [paste relevant handler code]
Tech stack: Express, PostgreSQL, deployed on Lambda.
Plan:
1. Add Redis ElastiCache cluster
2. Create cache middleware
3. Cache GET /users and GET /products (TTL 5min)
4. Add cache invalidation on POST/PUT/DELETE
5. Add monitoring"

# Pipe longer prompts via stdin
echo "full context and plan here..." | kimi-advisor review -
```

### `decompose` — Break down into parallel/sequential tasks

Include full scope, tech stack, and component dependencies.

```bash
kimi-advisor decompose "Migrate REST API to GraphQL. Stack: Express (15 endpoints), PostgreSQL with Prisma, JWT auth, deployed on AWS Lambda via CDK. Endpoints: GET/POST /users, GET/POST/PUT /products, GET /orders... Must maintain REST during migration for mobile clients on older versions."
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

**Important:** Kimi has NO access to the codebase, files, or any context beyond what you pass in the prompt. You must include all relevant code, architecture details, constraints, and examples directly in the prompt as plain text. Never reference file paths or assume Kimi can look anything up.

### Commands

```bash
# Ask a question — include full context inline
kimi-advisor ask "We have a Node.js API serving 10k req/s with this data model: [paste schema]. Sessions are stored in PostgreSQL. Should we move session storage to Redis or Memcached? Constraints: team has no Redis experience, budget is limited."

# Review a plan — include the plan AND the relevant context
kimi-advisor review "Context: React Native app with Expo, using Zustand for state. Current auth is email/password via Cognito.
Plan:
1. Add Google OAuth provider in Cognito
2. Install expo-auth-session
3. Create useGoogleAuth hook
4. Add Google Sign-In button to LoginScreen
5. Map Google profile to existing user model"

# Decompose a task — describe the full scope with technical details
kimi-advisor decompose "Migrate a REST API (Express, 15 endpoints, PostgreSQL with Prisma ORM, deployed on AWS Lambda via CDK) to GraphQL. Current endpoints: [list them]. Auth is JWT-based. Need to maintain backwards compatibility during migration."

# Attach files directly instead of pasting
kimi-advisor ask "Review this schema" -f schema.prisma
kimi-advisor review "Is this migration safe?" -f migration.sql -f screenshot.png

# Pipe long input via stdin for larger prompts
echo "full context here..." | kimi-advisor review -
```

### When to use

**ask** — Architecture decisions, technology choices, trade-off analysis, unfamiliar domains. Always include: the current stack, constraints, what you've considered so far.

**review** — Validate your implementation plan before starting. Always include: the plan itself, the codebase context (relevant code snippets, architecture), and the goal.

**decompose** — Large migrations, multi-component features. Always include: full task description, tech stack, dependencies between components, constraints.

### Prompt quality checklist

Before calling kimi-advisor, verify your prompt includes:
- [ ] The actual code or schema (not just file names)
- [ ] Tech stack and framework versions
- [ ] Constraints (team skills, budget, timeline, existing infra)
- [ ] What you've already considered or tried
- [ ] The specific question or decision point
````

### Optional: Auto-review plans with a hook

Add a `SubagentStop` hook to your project's `.claude/settings.json` so Claude automatically calls `kimi-advisor review` whenever a Plan agent finishes — before exiting plan mode:

```json
{
  "hooks": {
    "SubagentStop": [
      {
        "matcher": "Plan",
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"decision\": \"block\", \"reason\": \"Before exiting plan mode, run kimi-advisor review via Bash with the full plan content. If you already did, proceed to ExitPlanMode.\"}'"
          }
        ]
      }
    ]
  }
}
```

This blocks the Plan agent's return and reminds Claude to get Kimi's feedback on the plan. The `matcher: "Plan"` ensures it only fires for Plan agents, not Explore or Bash.

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
