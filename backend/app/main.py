"""Local FastAPI control plane for the MongoDB research prototype."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.demo import router
from app.demo.events import DemoStore


def create_app(*, demo_store: DemoStore | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # External services connect lazily. Discovery stays available offline.
        try:
            yield
        finally:
            await application.state.demo_store.close()

    application = FastAPI(title="Dependency-Aware MCP", lifespan=lifespan)
    application.state.demo_store = demo_store or DemoStore()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    application.include_router(router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
