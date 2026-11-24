import uvicorn

from family_ai_api.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "family_ai_api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        # Trusted proxies are handled inside create_app(). Uvicorn's access log
        # would otherwise persist request query strings.
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
