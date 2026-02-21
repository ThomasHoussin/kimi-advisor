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
Question: Has "kimi-advisor" been actually executed during this session to review or challenge the current plan?

Valid evidence of execution includes:
- A Bash tool call containing "kimi-advisor review", "kimi-advisor ask", or "kimi-advisor decompose"
- A piped invocation like "cat ... | kimi-advisor review" or "echo ... | kimi-advisor review"
- Tool result/output blocks showing kimi-advisor's response (e.g., "## Plan Review", "## Task Decomposition", "## Answer", recommendations, issues found)
- The assistant discussing or incorporating specific feedback that came from kimi-advisor

What does NOT count as evidence:
- Mentions in system-reminder tags, CLAUDE.md instructions, or hook additionalContext (these are static instructions, not executions)
- The assistant merely suggesting to run kimi-advisor without actually doing it
- Vague claims like "I considered the advisor's input" without concrete output

Respond with ONLY a JSON object, no other text:
{"executed": true} or {"executed": false}`;

const TRANSCRIPT_WINDOW = 80_000;

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

/**
 * Extract the most relevant portion of the transcript for analysis.
 * Search for execution-specific markers (tool invocations and output headings)
 * rather than just "kimi-advisor" which matches CLAUDE.md documentation references.
 * Falls back to the tail if no match.
 */
function extractRelevantTranscript(raw) {
    if (raw.length <= TRANSCRIPT_WINDOW) {
        return raw;
    }

    // Ordered by specificity: invocations first, then output headings
    const markers = [
        "| kimi-advisor",        // piped invocation
        "kimi-advisor review",   // direct invocations
        "kimi-advisor ask",
        "kimi-advisor decompose",
        "## Plan Review",        // output headings (lower priority)
        "## Task Decomposition",
        "## Answer",
    ];

    // Find the latest match across all markers
    let bestIdx = -1;
    for (const marker of markers) {
        const idx = raw.lastIndexOf(marker);
        if (idx > bestIdx) {
            bestIdx = idx;
        }
    }

    if (bestIdx === -1) {
        // No evidence at all — give Haiku the tail to confirm absence
        return raw.slice(-TRANSCRIPT_WINDOW);
    }

    // Center a window around the best match
    const half = Math.floor(TRANSCRIPT_WINDOW / 2);
    let start = Math.max(0, bestIdx - half);
    let end = start + TRANSCRIPT_WINDOW;

    if (end > raw.length) {
        end = raw.length;
        start = Math.max(0, end - TRANSCRIPT_WINDOW);
    }

    return raw.slice(start, end);
}

function allow() {
    console.log(
        JSON.stringify({
            hookSpecificOutput: {
                hookEventName: "PreToolUse",
                permissionDecision: "allow",
                permissionDecisionReason: "kimi-advisor was executed.",
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
                    'kimi-advisor was not executed. Run kimi-advisor review "<plan summary>" first to get a second opinion before exiting plan mode.',
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

        const raw = readFileSync(transcript_path, "utf8");
        const transcript = extractRelevantTranscript(raw);

        const fullPrompt = `${PROMPT}\n\n<transcript>\n${transcript}\n</transcript>`;

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
            // Log Haiku's raw response to stderr for debugging false negatives
            process.stderr.write(
                `[pre-exit-plan-mode] Haiku denied. Raw response: ${response.trim()}\n`,
            );
            deny();
        }
    } catch {
        // Any error → exit 0 silently → normal behavior
        process.exit(0);
    }
}

main();
