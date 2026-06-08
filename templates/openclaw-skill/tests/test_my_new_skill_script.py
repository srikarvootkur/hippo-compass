import importlib.util
import json
import sys
from pathlib import Path


def load_script():
    script_path = Path(__file__).parents[1] / "scripts" / "my_new_skill.py"
    spec = importlib.util.spec_from_file_location("my_new_skill_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_script_posts_expected_request(monkeypatch, capsys) -> None:
    module = load_script()
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"status":"ok"}'

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["body"] = json.loads(request.data.decode())
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("HIPPO_COMPASS_API_URL", "http://assistant-api:8080")
    monkeypatch.setenv("HIPPO_COMPASS_API_KEY", "secret")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "argv", ["my_new_skill.py", "--input", "example"])

    module.main()

    assert seen["url"] == "http://assistant-api:8080/replace-with-real-endpoint"
    assert seen["headers"]["X-assistant-api-key"] == "secret"
    assert seen["body"] == {"input": "example"}
    assert seen["timeout"] == 30
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
