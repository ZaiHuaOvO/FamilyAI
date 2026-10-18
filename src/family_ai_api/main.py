from fastapi import FastAPI

from family_ai_api.routers import health


def create_app() -> FastAPI:
    app = FastAPI(
        title="Family AI API",
        description="家庭局域网内使用的本地大模型 API",
        version="0.1.0",
    )
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
