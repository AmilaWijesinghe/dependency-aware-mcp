"""Browser-test fixture ONLY. Never use this command to present the demo.

Uses in-memory persistence and model substitutes from tests/demo_support.py;
all graph/MCP/OCC/Auditor-service/dependency/recovery code still executes.
"""

import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project))
sys.path.insert(0, str(project / "tests"))

from demo_support import IsolatedResearchStack
from app.main import create_app

logging.getLogger().setLevel(logging.ERROR)

app = create_app()
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    async with IsolatedResearchStack():
        async with original_lifespan(application):
            yield


app.router.lifespan_context = lifespan

if __name__ == "__main__":
    print("TEST FIXTURE: model and MongoDB substitutes enabled", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="warning")
