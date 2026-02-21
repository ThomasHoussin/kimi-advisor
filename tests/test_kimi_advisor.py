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
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            client = kimi_advisor.KimiClient()
            with pytest.raises(click.ClickException, match="empty response"):
                client.query("ask", "test", 8192)

    def test_none_content(self, mock_env, mock_response):
        mock_response.choices[0].message.content = None
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
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
                buffer=MagicMock(
                    read=lambda: "accents éàü et emoji 🎉".encode("utf-8")
                ),
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

    def test_none_argument_tty(self, monkeypatch):
        """No argument + interactive terminal → None (triggers 'No input' error)."""
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        assert kimi_advisor.read_input(None) is None

    def test_stdin_autodetect(self, monkeypatch):
        """No argument + piped stdin → reads stdin automatically."""
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(
                isatty=lambda: False,
                buffer=MagicMock(read=lambda: b"piped input\n"),
            ),
        )
        assert kimi_advisor.read_input(None) == "piped input"

    def test_stdin_autodetect_empty(self, monkeypatch):
        """No argument + empty piped stdin → None."""
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(
                isatty=lambda: False,
                buffer=MagicMock(read=lambda: b""),
            ),
        )
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

    def test_ask_stdin_autodetect(self, runner, mock_env, mock_response):
        """No argument + piped stdin → reads stdin automatically (heredoc support)."""
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = (
                mock_response
            )
            result = runner.invoke(kimi_advisor.cli, ["ask"], input="piped question\n")
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

    def test_file_option_text(self, runner, mock_env, mock_response, tmp_path):
        code_file = tmp_path / "app.py"
        code_file.write_text("def hello(): pass", encoding="utf-8")
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            result = runner.invoke(
                kimi_advisor.cli,
                ["ask", "explain this code", "-f", str(code_file)],
            )
            assert result.exit_code == 0
            call_kwargs = mock_create.call_args[1]
            user_content = call_kwargs["messages"][1]["content"]
            assert isinstance(user_content, list)

    def test_file_option_image(self, runner, mock_env, mock_response, tmp_path):
        img_file = tmp_path / "screenshot.png"
        img_file.write_bytes(b"\x89PNG" + b"\x00" * 50)
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            result = runner.invoke(
                kimi_advisor.cli,
                ["ask", "describe this", "-f", str(img_file)],
            )
            assert result.exit_code == 0
            call_kwargs = mock_create.call_args[1]
            user_content = call_kwargs["messages"][1]["content"]
            assert any(part["type"] == "image_url" for part in user_content)

    def test_file_option_multiple(self, runner, mock_env, mock_response, tmp_path):
        f1 = tmp_path / "a.py"
        f1.write_text("a = 1", encoding="utf-8")
        f2 = tmp_path / "b.py"
        f2.write_text("b = 2", encoding="utf-8")
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            result = runner.invoke(
                kimi_advisor.cli,
                ["ask", "compare", "-f", str(f1), "-f", str(f2)],
            )
            assert result.exit_code == 0

    def test_file_not_found_error(self, runner, mock_env):
        with patch.object(kimi_advisor, "OpenAI"):
            result = runner.invoke(
                kimi_advisor.cli,
                ["ask", "explain", "-f", "/nonexistent/file.py"],
            )
            assert result.exit_code != 0
            assert "File not found" in result.output

    def test_no_files_backward_compatible(self, runner, mock_env, mock_response):
        """Queries without -f still send plain string content."""
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            runner.invoke(kimi_advisor.cli, ["ask", "hello"])
            call_kwargs = mock_create.call_args[1]
            user_content = call_kwargs["messages"][1]["content"]
            assert isinstance(user_content, str)

    def test_review_files_only(self, runner, mock_env, mock_response, tmp_path):
        """review with -f but no text argument should succeed with default prompt."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(
            "# Migration Plan\n1. Step one\n2. Step two", encoding="utf-8"
        )
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            result = runner.invoke(
                kimi_advisor.cli,
                ["review", "-f", str(plan_file)],
            )
            assert result.exit_code == 0
            assert "Test answer" in result.output
            call_kwargs = mock_create.call_args[1]
            user_content = call_kwargs["messages"][1]["content"]
            assert isinstance(user_content, list)
            assert user_content[0]["text"] == "Review the attached files."

    def test_ask_files_only(self, runner, mock_env, mock_response, tmp_path):
        """ask with -f but no text argument should succeed with default prompt."""
        code_file = tmp_path / "code.py"
        code_file.write_text("def foo(): pass", encoding="utf-8")
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            result = runner.invoke(
                kimi_advisor.cli,
                ["ask", "-f", str(code_file)],
            )
            assert result.exit_code == 0
            call_kwargs = mock_create.call_args[1]
            user_content = call_kwargs["messages"][1]["content"]
            assert user_content[0]["text"] == "Answer based on the attached files."

    def test_decompose_files_only(self, runner, mock_env, mock_response, tmp_path):
        """decompose with -f but no text argument should succeed with default prompt."""
        task_file = tmp_path / "task.md"
        task_file.write_text("# Big Task\nMigrate everything", encoding="utf-8")
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            result = runner.invoke(
                kimi_advisor.cli,
                ["decompose", "-f", str(task_file)],
            )
            assert result.exit_code == 0
            call_kwargs = mock_create.call_args[1]
            user_content = call_kwargs["messages"][1]["content"]
            assert (
                user_content[0]["text"]
                == "Decompose the task described in the attached files."
            )

    def test_review_text_with_files(self, runner, mock_env, mock_response, tmp_path):
        """review with both text and -f should use the provided text, not default."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan content", encoding="utf-8")
        with patch.object(kimi_advisor, "OpenAI") as mock_openai:
            mock_create = mock_openai.return_value.chat.completions.create
            mock_create.return_value = mock_response
            result = runner.invoke(
                kimi_advisor.cli,
                ["review", "Check this plan carefully", "-f", str(plan_file)],
            )
            assert result.exit_code == 0
            call_kwargs = mock_create.call_args[1]
            user_content = call_kwargs["messages"][1]["content"]
            assert isinstance(user_content, list)
            assert user_content[0]["text"] == "Check this plan carefully"

    def test_no_input_error_shows_file_usage(self, runner, mock_env):
        """Error message should mention -f as a valid usage pattern."""
        with patch.object(kimi_advisor, "OpenAI"):
            result = runner.invoke(kimi_advisor.cli, ["ask"])
            assert result.exit_code != 0
            assert "-f" in result.output


# --- _is_image_file ---


class TestIsImageFile:
    @pytest.mark.parametrize("ext", [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"])
    def test_image_extensions(self, ext):
        assert kimi_advisor._is_image_file(Path(f"photo{ext}")) is True

    @pytest.mark.parametrize("ext", [".py", ".txt", ".md", ".json", ".csv", ".svg", ""])
    def test_non_image_extensions(self, ext):
        assert kimi_advisor._is_image_file(Path(f"file{ext}")) is False

    def test_case_insensitive(self):
        assert kimi_advisor._is_image_file(Path("photo.PNG")) is True
        assert kimi_advisor._is_image_file(Path("photo.Jpg")) is True


# --- _read_file_content ---


class TestReadFileContent:
    def test_file_not_found(self, tmp_path):
        path = tmp_path / "nonexistent.txt"
        with pytest.raises(click.ClickException, match="File not found"):
            kimi_advisor._read_file_content(path)

    def test_error_mentions_path_hint(self, tmp_path):
        path = tmp_path / "missing.txt"
        with pytest.raises(click.ClickException, match="Verify the path"):
            kimi_advisor._read_file_content(path)

    def test_directory_not_file(self, tmp_path):
        with pytest.raises(click.ClickException, match="Not a file"):
            kimi_advisor._read_file_content(tmp_path)

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.txt"
        path.write_text("")
        with pytest.raises(click.ClickException, match="File is empty"):
            kimi_advisor._read_file_content(path)

    def test_file_too_large(self, tmp_path):
        path = tmp_path / "huge.txt"
        path.write_bytes(b"x" * (kimi_advisor.MAX_FILE_SIZE + 1))
        with pytest.raises(click.ClickException, match="File too large"):
            kimi_advisor._read_file_content(path)

    def test_read_text_file(self, tmp_path):
        path = tmp_path / "hello.py"
        path.write_text("print('hello')", encoding="utf-8")
        typ, data, name = kimi_advisor._read_file_content(path)
        assert typ == "text"
        assert data == "print('hello')"
        assert name == "hello.py"

    def test_read_image_file(self, tmp_path):
        path = tmp_path / "img.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        typ, data, name = kimi_advisor._read_file_content(path)
        assert typ == "image"
        assert data.startswith("data:image/png;base64,")
        assert name == "img.png"

    def test_non_utf8_text_replaced(self, tmp_path):
        path = tmp_path / "latin.txt"
        path.write_bytes(b"caf\xe9 cr\xe8me")
        typ, data, name = kimi_advisor._read_file_content(path)
        assert typ == "text"
        assert "\ufffd" in data

    def test_svg_treated_as_text(self, tmp_path):
        path = tmp_path / "icon.svg"
        path.write_text("<svg></svg>", encoding="utf-8")
        typ, data, name = kimi_advisor._read_file_content(path)
        assert typ == "text"
        assert "<svg>" in data


# --- _process_files ---


class TestProcessFiles:
    def test_empty_tuple(self):
        assert kimi_advisor._process_files(()) == []

    def test_single_text_file(self, tmp_path):
        path = tmp_path / "code.py"
        path.write_text("x = 1", encoding="utf-8")
        result = kimi_advisor._process_files((str(path),))
        assert len(result) == 1
        assert result[0][0] == "text"
        assert result[0][2] == "code.py"

    def test_mixed_files(self, tmp_path):
        txt = tmp_path / "notes.md"
        txt.write_text("# Notes", encoding="utf-8")
        img = tmp_path / "pic.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 100)
        result = kimi_advisor._process_files((str(txt), str(img)))
        assert result[0][0] == "text"
        assert result[1][0] == "image"

    def test_deduplication(self, tmp_path):
        path = tmp_path / "file.txt"
        path.write_text("hello", encoding="utf-8")
        result = kimi_advisor._process_files((str(path), str(path)))
        assert len(result) == 1

    def test_total_size_exceeded(self, tmp_path):
        # Create 11 distinct files each just under the per-file limit
        paths = []
        for i in range(11):
            p = tmp_path / f"big{i}.txt"
            p.write_bytes(b"x" * (kimi_advisor.MAX_FILE_SIZE - 1))
            paths.append(str(p))
        with pytest.raises(click.ClickException, match="Total attachment size"):
            kimi_advisor._process_files(tuple(paths))


# --- _build_user_content ---


class TestBuildUserContent:
    def test_no_attachments_returns_string(self):
        result = kimi_advisor._build_user_content("hello", [])
        assert result == "hello"
        assert isinstance(result, str)

    def test_text_attachment(self):
        attachments = [("text", "print('hi')", "main.py")]
        result = kimi_advisor._build_user_content("explain this", attachments)
        assert isinstance(result, list)
        assert len(result) == 2  # prompt + file context
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "explain this"
        assert result[1]["type"] == "text"
        assert "main.py" in result[1]["text"]

    def test_image_attachment(self):
        attachments = [("image", "data:image/png;base64,abc123", "photo.png")]
        result = kimi_advisor._build_user_content("describe this", attachments)
        assert isinstance(result, list)
        assert len(result) == 2  # prompt + image
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "describe this"
        assert result[1]["type"] == "image_url"
        assert result[1]["image_url"]["url"] == "data:image/png;base64,abc123"

    def test_mixed_attachments_ordering(self):
        attachments = [
            ("text", "code here", "app.py"),
            ("image", "data:image/png;base64,xyz", "screenshot.png"),
        ]
        result = kimi_advisor._build_user_content("review this", attachments)
        assert isinstance(result, list)
        assert len(result) == 3  # prompt, text context, image
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "review this"
        assert result[1]["type"] == "text"
        assert "app.py" in result[1]["text"]
        assert result[2]["type"] == "image_url"
