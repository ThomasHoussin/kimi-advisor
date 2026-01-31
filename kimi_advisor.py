#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=1.40.0",
#     "click>=8.1.0",
#     "python-dotenv>=1.0.0",
# ]
# [tool.uv]
# exclude-newer = "2026-02-01T00:00:00Z"
# ///
"""kimi-advisor: Get a second opinion from Kimi K2.5."""

import base64
import json
import os
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv
from openai import OpenAI

SCRIPT_DIR = Path(__file__).resolve().parent

load_dotenv(SCRIPT_DIR / ".env.local")
load_dotenv(SCRIPT_DIR / ".env")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"
DEFAULT_MODEL = "kimi-k2.5"
DEFAULT_MAX_TOKENS = 8192
MAX_RETRIES = 3

MAX_FILE_SIZE_MB = 1
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_TOTAL_SIZE_MB = 10
MAX_TOTAL_SIZE = MAX_TOTAL_SIZE_MB * 1024 * 1024
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


def _load_prompt(name: str) -> str:
    """Load a system prompt from prompts/{name}.md."""
    path = SCRIPT_DIR / "prompts" / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise click.ClickException(f"Prompt file not found: {path}") from None


SYSTEM_PROMPTS = {mode: _load_prompt(mode) for mode in ("ask", "review", "decompose")}


class KimiClient:
    """Client for Kimi K2.5 via Moonshot API."""

    def __init__(self):
        api_key = os.environ.get("KIMI_API_KEY", "").strip()
        if not api_key:
            raise click.ClickException(
                "KIMI_API_KEY not set. Add it to .env.local or export it. "
                "Get your key at https://platform.moonshot.ai"
            )
        self.client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("KIMI_API_BASE", DEFAULT_BASE_URL),
        )
        self.model = os.environ.get("KIMI_MODEL", DEFAULT_MODEL)

    def query(
        self,
        mode: str,
        prompt: str,
        max_tokens: int,
        attachments: list[tuple[str, str, str]] | None = None,
    ) -> tuple[str, str]:
        """Query Kimi and return (reasoning, answer)."""
        system_prompt = SYSTEM_PROMPTS[mode]
        user_content = _build_user_content(prompt, attachments or [])
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=1.0,
                    max_tokens=max_tokens,
                )
                if not response.choices:
                    raise click.ClickException(
                        "API returned empty response. Please try again."
                    ) from None
                message = response.choices[0].message
                reasoning = getattr(message, "reasoning_content", None) or ""
                content = message.content or ""
                return reasoning, content

            except Exception as e:
                last_error = e
                status = getattr(e, "status_code", None)

                if status == 401:
                    raise click.ClickException(
                        "Authentication failed. Check your KIMI_API_KEY."
                    ) from None

                if status == 429 or (status is not None and status >= 500):
                    if attempt < MAX_RETRIES - 1:
                        wait = 2**attempt
                        click.echo(
                            f"Retrying in {wait}s ({type(e).__name__})...",
                            err=True,
                        )
                        time.sleep(wait)
                    continue

                raise click.ClickException(f"({type(e).__name__}): {e}") from None

        raise click.ClickException(
            f"Failed after {MAX_RETRIES} retries: ({type(last_error).__name__}): {last_error}"
        ) from None


def read_input(argument: str | None) -> str | None:
    """Read input from argument or stdin."""
    if argument == "-":
        if sys.stdin.isatty():
            return None
        raw = sys.stdin.buffer.read()
        text = raw.decode("utf-8", errors="replace").strip()
        return text or None
    if argument is not None and not argument.strip():
        return None
    return argument


def _is_image_file(path: Path) -> bool:
    """Check if a file is an image based on extension."""
    return path.suffix.lower() in IMAGE_MIME_TYPES


def _read_file_content(path: Path) -> tuple[str, str, str]:
    """Read a file and return (type, data, filename).

    Returns ("text", content, name) or ("image", data_uri, name).
    Raises click.ClickException on any error.
    """
    resolved = path.resolve()
    try:
        stat = resolved.stat()
    except FileNotFoundError:
        raise click.ClickException(
            f"File not found: {path}\n"
            "Verify the path is correct. On Windows, check for backslash escaping."
        ) from None
    except IsADirectoryError:
        raise click.ClickException(f"Not a file (is a directory): {path}") from None
    except PermissionError:
        raise click.ClickException(f"Permission denied: {path}") from None

    if not resolved.is_file():
        raise click.ClickException(f"Not a file (is a directory): {path}")

    size = stat.st_size
    if size == 0:
        raise click.ClickException(f"File is empty: {path}")
    if size > MAX_FILE_SIZE:
        size_mb = size / (1024 * 1024)
        raise click.ClickException(
            f"File too large: {path.name} ({size_mb:.1f} MB). "
            f"Maximum is {MAX_FILE_SIZE_MB} MB."
        )

    name = resolved.name

    if _is_image_file(resolved):
        try:
            raw = resolved.read_bytes()
        except PermissionError:
            raise click.ClickException(f"Permission denied: {path}") from None
        mime = IMAGE_MIME_TYPES[resolved.suffix.lower()]
        b64 = base64.b64encode(raw).decode("ascii")
        return ("image", f"data:{mime};base64,{b64}", name)

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        raise click.ClickException(f"Permission denied: {path}") from None
    if "\ufffd" in text:
        click.echo(f"Warning: {name} contains non-UTF-8 bytes (replaced)", err=True)
    return ("text", text, name)


def _process_files(file_paths: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """Process file paths and return list of (type, data, filename)."""
    if not file_paths:
        return []

    seen: set[Path] = set()
    results: list[tuple[str, str, str]] = []
    total_size = 0

    for file_str in file_paths:
        resolved = Path(file_str).resolve()
        if resolved in seen:
            click.echo(f"Warning: skipping duplicate file: {resolved.name}", err=True)
            continue
        seen.add(resolved)

        try:
            total_size += resolved.stat().st_size
        except (FileNotFoundError, PermissionError):
            pass  # _read_file_content will raise a proper error
        if total_size > MAX_TOTAL_SIZE:
            total_mb = total_size / (1024 * 1024)
            raise click.ClickException(
                f"Total attachment size ({total_mb:.1f} MB) exceeds "
                f"{MAX_TOTAL_SIZE_MB} MB limit. Attach fewer files."
            )

        results.append(_read_file_content(Path(file_str)))

    return results


def _build_user_content(
    prompt: str, attachments: list[tuple[str, str, str]]
) -> str | list[dict]:
    """Build user message content, optionally with file attachments."""
    if not attachments:
        return prompt

    parts: list[dict] = []

    # 1. User question first
    parts.append({"type": "text", "text": prompt})

    # 2. Text file contents
    for typ, data, name in attachments:
        if typ == "text":
            parts.append(
                {"type": "text", "text": f"**File: {name}**\n```\n{data}\n```"}
            )

    # 3. Image attachments
    for typ, data_uri, name in attachments:
        if typ == "image":
            parts.append({"type": "image_url", "image_url": {"url": data_uri}})

    return parts


def format_output(
    reasoning: str,
    answer: str,
    show_reasoning: bool = False,
    as_json: bool = False,
) -> str:
    """Format the output for display."""
    if as_json:
        data = {"answer": answer}
        if show_reasoning and reasoning:
            data["reasoning"] = reasoning
        return json.dumps(data, indent=2, ensure_ascii=False)

    parts = []
    if show_reasoning and reasoning:
        parts.append("<reasoning>\n" + reasoning + "\n</reasoning>\n")
    parts.append(answer)
    return "\n".join(parts)


@click.group()
@click.version_option(version="0.1.0", prog_name="kimi-advisor")
def cli():
    """Get a second opinion from Kimi K2.5."""


def _common_options(f):
    """Shared options for all commands."""
    f = click.option("--show-reasoning", is_flag=True, help="Display thinking process")(
        f
    )
    f = click.option(
        "--max-tokens", default=DEFAULT_MAX_TOKENS, type=int, help="Output token limit"
    )(f)
    f = click.option("--json", "as_json", is_flag=True, help="Structured JSON output")(
        f
    )
    f = click.option(
        "--file",
        "-f",
        "files",
        multiple=True,
        type=click.Path(),
        help="Attach file(s). Text included as context, images as vision input. Repeatable.",
    )(f)
    return f


def _run_command(
    mode: str,
    prompt: str | None,
    show_reasoning: bool,
    max_tokens: int,
    as_json: bool,
    files: tuple[str, ...] = (),
):
    """Shared execution logic for all commands."""
    if not prompt:
        raise click.ClickException(
            f'No input provided. Usage: kimi-advisor {mode} "your text"'
        )

    attachments = _process_files(files)

    client = KimiClient()
    reasoning, answer = client.query(mode, prompt, max_tokens, attachments=attachments)
    output = format_output(reasoning, answer, show_reasoning, as_json)
    click.echo(output)


@cli.command()
@click.argument("question", required=False)
@_common_options
def ask(question, show_reasoning, max_tokens, as_json, files):
    """Ask a question, get advice."""
    prompt = read_input(question)
    _run_command("ask", prompt, show_reasoning, max_tokens, as_json, files=files)


@cli.command()
@click.argument("plan", required=False)
@_common_options
def review(plan, show_reasoning, max_tokens, as_json, files):
    """Review and critique a plan."""
    prompt = read_input(plan)
    _run_command("review", prompt, show_reasoning, max_tokens, as_json, files=files)


@cli.command()
@click.argument("task", required=False)
@_common_options
def decompose(task, show_reasoning, max_tokens, as_json, files):
    """Decompose a task into parallel/sequential subtasks."""
    prompt = read_input(task)
    _run_command("decompose", prompt, show_reasoning, max_tokens, as_json, files=files)


if __name__ == "__main__":
    cli()
