import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from family_ai_api import __main__ as entrypoint
from family_ai_api.config import Settings


def test_main_uses_settings(monkeypatch) -> None:
    calls: dict = {}

    def fake_run(app: str, **kwargs: object) -> None:
        calls["app"] = app
        calls.update(kwargs)

    monkeypatch.setattr(entrypoint.uvicorn, "run", fake_run)
    monkeypatch.setattr(
        entrypoint,
        "get_settings",
        lambda: Settings(app_host="0.0.0.0", app_port=9000),
    )

    entrypoint.main()

    assert calls == {
        "app": "family_ai_api.main:app",
        "host": "0.0.0.0",
        "port": 9000,
        "proxy_headers": False,
        "access_log": False,
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_entrypoint_keeps_query_strings_out_of_logs(tmp_path: Path) -> None:
    port = _free_port()
    env = os.environ.copy()
    env.update(
        {
            "APP_HOST": "127.0.0.1",
            "APP_PORT": str(port),
            "API_ACCESS_TOKEN": "test-token",
            "MEMBERS_DB_PATH": str(tmp_path / "members.db"),
            "MEMORY_DB_PATH": str(tmp_path / "memory.db"),
            "AUTO_MEMORY_ENABLED": "false",
            "FORWARDED_ALLOW_IPS": "127.0.0.1,::1",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "family_ai_api"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    marker = "query-marker-7b1c"
    try:
        base_url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if httpx.get(f"{base_url}/api/v1/health", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            pytest.fail("server did not start")

        response = httpx.get(f"{base_url}/api/v1/health?query={marker}", timeout=5)
        assert response.status_code == 200
        time.sleep(0.2)
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=15)

    assert marker not in output

