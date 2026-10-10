"""End to end: a served app with the default hook loader and a real `hooks.toml`."""

import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import cast

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from tests.server.conftest import BASE_URL, MakeApp, create, finished, status, wait_until

HOOK_URL = "https://hooks.test/run"


def write_hooks(config_dir: Path, text: str) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "hooks.toml").write_text(text)


def signed(request: httpx.Request, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), request.content, hashlib.sha256).hexdigest()
    return request.headers["X-Wosarcher-Signature"] == expected


def sent(route: respx.Route, n: int) -> httpx.Request:
    return cast(httpx.Request, route.calls[n].request)


def run_once(make_app: MakeApp, query: str = "q") -> str:
    with TestClient(make_app(), base_url=BASE_URL) as client:
        run_id = create(client, {"query": query})
        finished(client, run_id)
        assert status(client, run_id) == "done"
    return run_id


def test_signed_webhook_with_command_header(make_app: MakeApp, config_dir: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("s3cret\n")
    write_hooks(
        config_dir,
        f"""
[[on_finish]]
url = "{HOOK_URL}"
secret_file = "{secret}"
headers = {{ Authorization = {{ value_command = ["printf", "Bearer tok"] }}, X-Plain = "plain" }}
""",
    )
    with respx.mock(assert_all_called=False) as router:
        route = router.post(HOOK_URL).respond(204)
        run_id = run_once(make_app)
        assert route.call_count == 1
        request = sent(route, 0)
        body = json.loads(request.content)
        assert (body["event"], body["run_id"], body["status"]) == ("run.finished", run_id, "done")
        assert body["report_path"].endswith("report.md")
        assert signed(request, "s3cret")
        assert request.headers["Authorization"] == "Bearer tok"
        assert request.headers["X-Plain"] == "plain"
        assert request.headers["Content-Type"] == "application/json"

        secret.write_text("rotated\n")
        run_once(make_app)
        assert route.call_count == 2
        assert signed(sent(route, 1), "rotated")


def test_redirect_not_followed(make_app: MakeApp, config_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    write_hooks(config_dir, f'[[on_finish]]\nurl = "{HOOK_URL}"\n')
    with respx.mock(assert_all_called=False) as router:
        route = router.post(HOOK_URL).respond(302, headers={"Location": "https://hooks.test/elsewhere"})
        other = router.route(url="https://hooks.test/elsewhere").respond(200)
        run_id = run_once(make_app)
        assert (route.call_count, other.call_count) == (1, 0)
    assert f"hook 1 (webhook) failed for run {run_id}: HTTP 302" in caplog.text


def test_command_hook_env(make_app: MakeApp, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_PROFILE", "workstation")
    monkeypatch.setenv("WOSARCHER_LLM__API_KEY", "provider-key")
    script = f'printf %s "$WA_HOOK_STATUS" > {tmp_path}/out; env > {tmp_path}/env.txt'
    write_hooks(config_dir, f"[[on_finish]]\ncommand = {json.dumps(['sh', '-c', script])}\n")
    with TestClient(make_app(), base_url=BASE_URL) as client:
        run_id = create(client, {"query": "q; rm -rf $HOME"})
        finished(client, run_id)
        wait_until(lambda: (tmp_path / "env.txt").is_file())
    assert (tmp_path / "out").read_text() == "done"
    env = (tmp_path / "env.txt").read_text()
    assert "WOSARCHER_PROFILE=workstation" in env
    assert "WOSARCHER_LLM__API_KEY" not in env
    assert "WA_HOOK_QUERY=q; rm -rf $HOME" in env
    assert f"WA_HOOK_RUN_ID={run_id}" in env


def test_failing_secret_command_skips_one_hook(
    make_app: MakeApp, config_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    write_hooks(
        config_dir,
        f"""
[[on_finish]]
url = "{HOOK_URL}"
secret_command = ["sh", "-c", "echo leaked-output; exit 1"]

[[on_finish]]
url = "{HOOK_URL}"
""",
    )
    with respx.mock(assert_all_called=False) as router:
        route = router.post(HOOK_URL).respond(200)
        run_id = run_once(make_app)
        assert route.call_count == 1
        assert "X-Wosarcher-Signature" not in sent(route, 0).headers
    assert f"hook 1 (webhook) failed for run {run_id}" in caplog.text
    assert "exited with status 1" in caplog.text
    assert "leaked-output" not in caplog.text


def test_invalid_file_fires_nothing(
    make_app: MakeApp, config_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    write_hooks(
        config_dir,
        f'[[on_finish]]\nurl = "{HOOK_URL}"\ncommand = ["touch", "{tmp_path}/touched"]\n',
    )
    with respx.mock(assert_all_called=False) as router:
        route = router.post(HOOK_URL).respond(200)
        run_once(make_app)
        assert route.call_count == 0
    assert not (tmp_path / "touched").exists()
    assert "hooks.toml" in caplog.text
    assert "entry 1: Value error, set exactly one of url, command" in caplog.text
