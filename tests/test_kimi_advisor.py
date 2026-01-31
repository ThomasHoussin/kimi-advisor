"""Tests for kimi_advisor.py."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from dotenv import load_dotenv
from click.testing import CliRunner

# Import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kimi_advisor


# --- dotenv loading ---


class TestDotenvLoading:
    def test_env_local_resolved_from_script_dir(self, tmp_path, monkeypatch):
        """Ensure .env.local is loaded relative to SCRIPT_DIR, not cwd."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("KIMI_TEST_VAR=from_script_dir\n")
        monkeypatch.delenv("KIMI_TEST_VAR", raising=False)
        load_dotenv(tmp_path / ".env.local")
        assert os.environ.get("KIMI_TEST_VAR") == "from_script_dir"
        monkeypatch.delenv("KIMI_TEST_VAR", raising=False)

    def test_env_local_not_found_in_wrong_cwd(self, tmp_path, monkeypatch):
        """Relative path would fail if cwd != script dir."""
        monkeypatch.delenv("KIMI_TEST_VAR2", raising=False)
        monkeypatch.chdir(tmp_path)
        load_dotenv(".env.local")  # no .env.local in tmp_path
        assert os.environ.get("KIMI_TEST_VAR2") is None


# --- _load_prompt ---


class TestLoadPrompt:
    def test_loads_existing_prompt(self):
        content = kimi_advisor._load_prompt("ask")
        assert "senior technical advisor" in content

    def test_missing_prompt_file(self, tmp_path):
        with patch.object(kimi_advisor, "SCRIPT_DIR", tmp_path):
            with pytest.raises(click.ClickException, match="Prompt file not found"):
                kimi_advisor._load_prompt("nonexistent")


# --- Fixtures ---


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "sk-fake-test-key")


@pytest.fixture
def mock_response():
    """Create a mock API response."""
    message = MagicMock()
    message.content = "Test answer"
    message.reasoning_content = "Test reasoning"
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    return response


# --- KimiClient.__init__ ---


class TestKimiClientInit:
    def test_success(self, mock_env):
        with patch.object(kimi_advisor, "OpenAI"):
            client = kimi_advisor.KimiClient()
            assert client.model == kimi_advisor.DEFAULT_MODEL

    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        with pytest.raises(click.ClickException, match="KIMI_API_KEY not set"):
            kimi_advisor.KimiClient()

    def test_empty_key(self, monkeypatch):
        monkeypatch.setenv("KIMI_API_KEY", "   ")
        with pytest.raises(click.ClickException, match="KIMI_API_KEY not set"):
            kimi_advisor.KimiClient()

    def test_custom_base_url(self, mock_env, monkeypatch):
        monkeypatch.setenv("KIMI_API_BASE", "https://custom.api/v1")
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            kimi_advisor.KimiClient()
            mock_openai.assert_called_once_with(
                api_key="sk-fake-test-key",
                base_url="https://custom.api/v1",
            )

    def test_custom_model(self, mock_env, monkeypatch):
        monkeypatch.setenv("KIMI_MODEL", "kimi-custom")
        with patch.object(kimi_advisor, "OpenAI"):
            client = kimi_advisor.KimiClient()
            assert client.model == "kimi-custom"


# --- KimiClient.query ---


class TestKimiClientQuery:
    def test_returns_reasoning_and_answer(self, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            client = kimi_advisor.KimiClient()
            reasoning, answer = client.query("ask", "test question", 8192)
            assert reasoning == "Test reasoning"
            assert answer == "Test answer"

    def test_missing_reasoning_content(self, mock_env, mock_response):
        del mock_response.choices[0].message.reasoning_content
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            client = kimi_advisor.KimiClient()
            reasoning, answer = client.query("ask", "test", 8192)
            assert reasoning == ""
            assert answer == "Test answer"

    def test_correct_system_prompt_per_mode(self, mock_env, mock_response):
        for mode in ("ask", "review", "decompose"):
            with patch.object(kimi_advisor, "OpenAI") as mock_openai:
                mock_create = mock_openai.return_value.chat.completions.create
                mock_create.return_value = mock_response
                client = kimi_advisor.KimiClient()
                client.query(mode, "test", 8192)
                call_kwargs = mock_create.call_args[1]
                system_msg = call_kwargs["messages"][0]["content"]
                assert system_msg == kimi_advisor.SYSTEM_PROMPTS[mode]

    def test_custom_max_tokens(self, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            client = kimi_advisor.KimiClient()
            client.query("ask", "test", 4096)
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["max_tokens"] == 4096

    def test_temperature_always_one(self, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            client = kimi_advisor.KimiClient()
            client.query("ask", "test", 8192)
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["temperature"] == 1.0

    def test_auth_error(self, mock_env):
        error = Exception("Unauthorized")
        error.status_code = 401
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.side_effect = error
            client = kimi_advisor.KimiClient()
            with pytest.raises(click.ClickException, match="Authentication failed"):
                client.query("ask", "test", 8192)

    def test_retry_on_rate_limit(self, mock_env, mock_response):
        error = Exception("Rate limited")
        error.status_code = 429
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.side_effect = [error, mock_response]
            client = kimi_advisor.KimiClient()
            with patch("time.sleep"):
                reasoning, answer = client.query("ask", "test", 8192)
            assert answer == "Test answer"
            assert mock_create.call_count == 2

    def test_retry_on_server_error(self, mock_env, mock_response):
        error = Exception("Server error")
        error.status_code = 500
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.side_effect = [error, error, mock_response]
            client = kimi_advisor.KimiClient()
            with patch("time.sleep"):
                reasoning, answer = client.query("ask", "test", 8192)
            assert answer == "Test answer"
            assert mock_create.call_count == 3

    def test_max_retries_exhausted(self, mock_env):
        error = Exception("Server error")
        error.status_code = 500
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.side_effect = error
            client = kimi_advisor.KimiClient()
            with patch("time.sleep"):
                with pytest.raises(click.ClickException, match="Failed after"):
                    client.query("ask", "test", 8192)

    def test_empty_choices_array(self, mock_env, mock_response):
        mock_response.choices = []
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = mock_response
            client = kimi_advisor.KimiClient()
            with pytest.raises(click.ClickException, match="empty response"):
                client.query("ask", "test", 8192)

    def test_none_content(self, mock_env, mock_response):
        mock_response.choices[0].message.content = None
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = mock_response
            client = kimi_advisor.KimiClient()
            reasoning, answer = client.query("ask", "test", 8192)
            assert answer == ""

    def test_non_retryable_error(self, mock_env):
        error = Exception("Bad request")
        error.status_code = 400
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.side_effect = error
            client = kimi_advisor.KimiClient()
            with pytest.raises(click.ClickException, match="Bad request"):
                client.query("ask", "test", 8192)


# --- read_input ---


class TestReadInput:
    def test_regular_argument(self):
        assert kimi_advisor.read_input("hello") == "hello"

    def test_stdin_dash(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(
                isatty=lambda: False,
                buffer=MagicMock(read=lambda: b"from stdin\n"),
            ),
        )
        assert kimi_advisor.read_input("-") == "from stdin"

    def test_stdin_dash_with_surrogate_bytes(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(
                isatty=lambda: False,
                buffer=MagicMock(read=lambda: b"hello \xed\xb2\x8f world"),
            ),
        )
        result = kimi_advisor.read_input("-")
        assert result is not None
        assert "hello" in result
        assert "world" in result
        assert "\ufffd" in result

    def test_stdin_dash_with_valid_utf8(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(
                isatty=lambda: False,
                buffer=MagicMock(read=lambda: "accents éàü et emoji 🎉".encode("utf-8")),
            ),
        )
        result = kimi_advisor.read_input("-")
        assert result == "accents éàü et emoji 🎉"

    def test_stdin_dash_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        assert kimi_advisor.read_input("-") is None

    def test_empty_string_argument(self):
        assert kimi_advisor.read_input("") is None

    def test_whitespace_argument(self):
        assert kimi_advisor.read_input("   ") is None

    def test_none_argument(self):
        assert kimi_advisor.read_input(None) is None


# --- format_output ---


class TestFormatOutput:
    def test_answer_only(self):
        result = kimi_advisor.format_output("reasoning", "answer", show_reasoning=False)
        assert result == "answer"
        assert "reasoning" not in result

    def test_with_reasoning(self):
        result = kimi_advisor.format_output(
            "reasoning text", "answer", show_reasoning=True
        )
        assert "<reasoning>" in result
        assert "reasoning text" in result
        assert "answer" in result

    def test_empty_reasoning_with_flag(self):
        result = kimi_advisor.format_output("", "answer", show_reasoning=True)
        assert result == "answer"
        assert "<reasoning>" not in result

    def test_json_output(self):
        result = kimi_advisor.format_output("reasoning", "answer", as_json=True)
        data = json.loads(result)
        assert data["answer"] == "answer"
        assert "reasoning" not in data

    def test_json_with_reasoning(self):
        result = kimi_advisor.format_output(
            "reasoning", "answer", show_reasoning=True, as_json=True
        )
        data = json.loads(result)
        assert data["answer"] == "answer"
        assert data["reasoning"] == "reasoning"


# --- CLI integration ---


class TestCLI:
    def test_help(self, runner):
        result = runner.invoke(kimi_advisor.cli, ["--help"])
        assert result.exit_code == 0
        assert "ask" in result.output
        assert "review" in result.output
        assert "decompose" in result.output

    def test_version(self, runner):
        result = runner.invoke(kimi_advisor.cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_ask_with_argument(self, runner, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            result = runner.invoke(kimi_advisor.cli, ["ask", "Redis vs Memcached?"])
            assert result.exit_code == 0
            assert "Test answer" in result.output

    def test_review_with_argument(self, runner, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            result = runner.invoke(kimi_advisor.cli, ["review", "1. Do X 2. Do Y"])
            assert result.exit_code == 0
            assert "Test answer" in result.output

    def test_decompose_with_argument(self, runner, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            result = runner.invoke(kimi_advisor.cli, ["decompose", "Big migration"])
            assert result.exit_code == 0
            assert "Test answer" in result.output

    def test_ask_with_stdin(self, runner, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            result = runner.invoke(
                kimi_advisor.cli, ["ask", "-"], input="stdin question\n"
            )
            assert result.exit_code == 0
            assert "Test answer" in result.output

    def test_no_input_error(self, runner, mock_env):
        with patch.object(kimi_advisor, "OpenAI"):
            result = runner.invoke(kimi_advisor.cli, ["ask"])
            assert result.exit_code != 0
            assert "No input" in result.output

    def test_show_reasoning_flag(self, runner, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            result = runner.invoke(
                kimi_advisor.cli, ["ask", "--show-reasoning", "test"]
            )
            assert result.exit_code == 0
            assert "<reasoning>" in result.output
            assert "Test reasoning" in result.output

    def test_json_flag(self, runner, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            result = runner.invoke(kimi_advisor.cli, ["ask", "--json", "test"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["answer"] == "Test answer"

    def test_max_tokens_option(self, runner, mock_env, mock_response):
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            result = runner.invoke(
                kimi_advisor.cli, ["ask", "--max-tokens", "2048", "test"]
            )
            assert result.exit_code == 0
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["max_tokens"] == 2048

    def test_missing_api_key(self, runner, monkeypatch):
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        result = runner.invoke(kimi_advisor.cli, ["ask", "test"])
        assert result.exit_code != 0
        assert "KIMI_API_KEY" in result.output
