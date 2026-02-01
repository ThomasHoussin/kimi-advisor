#!/usr/bin/env node

/**
 * Claude Code Hook: pre-exit-plan-mode.mjs
 *
 * PreToolUse hook for ExitPlanMode that verifies kimi-advisor was executed
 * to challenge the plan before allowing exit from plan mode.
 *
 * Uses Claude Haiku to analyze the session transcript for evidence of
 * kimi-advisor execution (not just mentions in reminders).
 *
 * On error, exits 0 silently → falls back to normal behavior.
 */

import { readFileSync } from "node:fs";
import { execSync } from "node:child_process";

const PROMPT = `Analyze this Claude Code session transcript (JSONL format).
Question: Has "kimi-advisor" been executed (via a Bash tool call) to review or challenge the current plan?

Look for evidence of kimi-advisor being actually called, such as:
- A Bash tool call containing "kimi-advisor review", "kimi-advisor ask", or "kimi-advisor decompose"
- Output from a kimi-advisor execution

A simple mention in a system-reminder, CLAUDE.md instruction, or hook additionalContext does NOT count as execution.
Only an actual tool call (Bash command) counts.

Respond with ONLY a JSON object, no other text:
{"executed": true} or {"executed": false}`;

const MAX_TRANSCRIPT_BYTES = 50_000;

function readStdin() {
    return new Promise((resolve) => {
        let data = "";
        process.stdin.setEncoding("utf8");
        process.stdin.on("data", (chunk) => {
            data += chunk;
        });
        process.stdin.on("end", () => resolve(data));
    });
}

function allow() {
    console.log(
        JSON.stringify({
            hookSpecificOutput: {
                hookEventName: "PreToolUse",
                permissionDecision: "allow",
                permissionDecisionReason: "kimi-advisor a bien été exécuté.",
            },
        }),
    );
}

function deny() {
    console.log(
        JSON.stringify({
            hookSpecificOutput: {
                hookEventName: "PreToolUse",
                permissionDecision: "deny",
                permissionDecisionReason:
                    'kimi-advisor n\'a pas été exécuté. Lancez d\'abord : kimi-advisor review "<contenu du plan>" pour obtenir un second avis avant de sortir du plan mode.',
            },
        }),
    );
}

async function main() {
    try {
        const input = JSON.parse(await readStdin());
        const { transcript_path } = input;

        if (!transcript_path) {
            // No transcript path available → fallback silently
            process.exit(0);
        }

        // Read transcript, truncate to last ~50KB for speed
        const raw = readFileSync(transcript_path, "utf8");
        const transcript =
            raw.length > MAX_TRANSCRIPT_BYTES
                ? raw.slice(-MAX_TRANSCRIPT_BYTES)
                : raw;

        const fullPrompt = `${PROMPT}\n\n--- TRANSCRIPT (last ${transcript.length} chars) ---\n${transcript}`;

        const response = execSync("claude -p --model haiku", {
            input: fullPrompt,
            encoding: "utf8",
            timeout: 90_000,
            maxBuffer: 1024 * 1024,
        });

        // Parse JSON from response (strip markdown fences if present)
        const cleaned = response
            .trim()
            .replace(/^```[\w]*\n?/, "")
            .replace(/\n?```$/, "");

        const result = JSON.parse(cleaned);

        if (result.executed) {
            allow();
        } else {
            deny();
        }
    } catch {
        // Any error → exit 0 silently → normal behavior
        process.exit(0);
    }
}

main();
