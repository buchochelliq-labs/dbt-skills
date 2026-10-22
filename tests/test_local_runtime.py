import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from dbt_skills.cli import main
from dbt_skills.project import (
    ProjectError,
    discover_project,
    initialize_project,
    load_runtime_config,
)
from dbt_skills.providers import (
    ModelReply,
    ModelProviderError,
    OpenAICompatibleProvider,
)
from dbt_skills.runtime import AgentRuntime


class LocalRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "analytics"
        self.root.mkdir()
        (self.root / "dbt_project.yml").write_text(
            "name: analytics_demo\nversion: '1.2.0'\nprofile: analytics_profile\n",
            encoding="utf-8",
        )

    def test_discover_project_from_nested_directory_and_manifest_presence(self):
        nested = self.root / "models" / "marts"
        nested.mkdir(parents=True)
        manifest = self.root / "target" / "manifest.json"
        manifest.parent.mkdir()
        manifest.write_text("{}", encoding="utf-8")

        project = discover_project(nested)

        self.assertEqual(project.root, self.root.resolve())
        self.assertEqual(project.name, "analytics_demo")
        self.assertEqual(project.version, "1.2.0")
        self.assertEqual(project.profile, "analytics_profile")
        self.assertTrue(project.manifest_available)
        self.assertEqual(project.to_json()["manifest_path"], str(manifest.resolve()))

    def test_discovery_requires_valid_dbt_project_config(self):
        with self.assertRaisesRegex(ProjectError, "No dbt_project.yml"):
            discover_project(Path(self.temp_dir.name))
        (self.root / "dbt_project.yml").write_text("not: [valid", encoding="utf-8")
        with self.assertRaisesRegex(ProjectError, "Invalid YAML"):
            discover_project(self.root)

    def test_init_writes_non_secret_config_and_refuses_to_overwrite(self):
        config_path = initialize_project(self.root)
        content = config_path.read_text(encoding="utf-8")
        self.assertIn('provider = "openai-compatible"', content)
        self.assertNotIn("OPENAI_API_KEY=", content)
        config = load_runtime_config(discover_project(self.root))
        self.assertEqual(config.provider, "openai-compatible")
        self.assertEqual(config.model, "")
        with self.assertRaisesRegex(ProjectError, "already exists"):
            initialize_project(self.root)

    def test_runtime_uses_injected_provider_with_untrusted_project_context(self):
        project = discover_project(self.root)

        class FixtureProvider:
            def __init__(self):
                self.request = None

            def complete(self, *, system_prompt, user_prompt):
                self.request = (system_prompt, user_prompt)
                return ModelReply("Project is analytics_demo.", "fixture", "fixed")

        provider = FixtureProvider()
        reply = AgentRuntime(provider).ask(project, "What is this project?")

        self.assertEqual(reply.text, "Project is analytics_demo.")
        self.assertIn('"project_name": "analytics_demo"', provider.request[0])
        self.assertIn("untrusted data", provider.request[0])
        self.assertEqual(provider.request[1], "What is this project?")

    def test_cli_inspects_and_initializes_without_hosted_services(self):
        from contextlib import redirect_stdout

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["inspect", "--project-dir", str(self.root)]), 0)
        self.assertIn("analytics_demo", output.getvalue())
        with redirect_stdout(output):
            self.assertEqual(main(["init", "--project-dir", str(self.root)]), 0)
        self.assertTrue((self.root / ".dbt-skills" / "config.toml").is_file())

    def test_cli_runs_scripted_session_through_provider_adapter(self):
        from contextlib import redirect_stdout

        initialize_project(self.root)
        response = io.BytesIO(
            json.dumps({"choices": [{"message": {"content": "Local model answer"}}]}).encode()
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-go-to-local"}):
            with patch(
                "dbt_skills.providers._open_request", return_value=response
            ) as open_url:
                with redirect_stdout(output):
                    result = main(
                        [
                            "ask",
                            "Summarize this project",
                            "--project-dir",
                            str(self.root),
                            "--model",
                            "fixture-model",
                        ]
                    )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), "Local model answer")
        request = open_url.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))

    def test_provider_sends_openai_compatible_request_and_environment_key(self):
        response_body = json.dumps(
            {"choices": [{"message": {"content": "Grounded answer"}}]}
        ).encode()
        response = io.BytesIO(response_body)
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.test/v1",
            model="fixture-model",
            api_key_env="DBT_SKILLS_TEST_KEY",
        )
        with patch.dict(os.environ, {"DBT_SKILLS_TEST_KEY": "fixture-secret"}):
            with patch(
                "dbt_skills.providers._open_request", return_value=response
            ) as open_url:
                reply = provider.complete(system_prompt="rules", user_prompt="question")

        request = open_url.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer fixture-secret")
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "rules"})
        self.assertEqual(payload["messages"][1], {"role": "user", "content": "question"})
        self.assertEqual(reply.text, "Grounded answer")

    def test_provider_rejects_insecure_remote_endpoints_and_sanitizes_http_errors(self):
        with self.assertRaisesRegex(ValueError, "only for localhost"):
            OpenAICompatibleProvider(
                base_url="http://model.example.test/v1", model="fixture-model"
            )
        provider = OpenAICompatibleProvider(
            base_url="https://api.example.test/v1", model="fixture-model"
        )
        from urllib.error import HTTPError

        failure = HTTPError(
            provider.url, 401, "Unauthorized", {}, io.BytesIO(b"private response")
        )
        with patch("dbt_skills.providers._open_request", side_effect=failure):
            with self.assertRaisesRegex(ModelProviderError, "HTTP 401") as error:
                provider.complete(system_prompt="rules", user_prompt="question")
        self.assertNotIn("private response", str(error.exception))

    def test_provider_bounds_response_size(self):
        class LargeResponse(io.BytesIO):
            def read(self, size=-1):
                return b"x" * (size + 1)

        provider = OpenAICompatibleProvider(
            base_url="http://localhost:11434/v1",
            model="fixture-model",
        )
        with patch(
            "dbt_skills.providers._open_request", return_value=LargeResponse(b"")
        ):
            with self.assertRaisesRegex(ModelProviderError, "8 MiB limit"):
                provider.complete(system_prompt="rules", user_prompt="question")

    def test_http_redirects_are_not_followed(self):
        requests = []

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(("POST", self.path))
                self.send_response(302)
                self.send_header(
                    "Location",
                    f"http://127.0.0.1:{self.server.server_port}/collect",
                )
                self.end_headers()

            def do_GET(self):
                requests.append(("GET", self.path))
                self.send_response(200)
                self.end_headers()

            def log_message(self, format, *args):
                del format, args

        server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OpenAICompatibleProvider(
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                model="fixture-model",
            )
            with self.assertRaisesRegex(ModelProviderError, "HTTP 302"):
                provider.complete(system_prompt="rules", user_prompt="question")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(requests, [("POST", "/v1/chat/completions")])


if __name__ == "__main__":
    unittest.main()
