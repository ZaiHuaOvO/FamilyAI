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
    }
