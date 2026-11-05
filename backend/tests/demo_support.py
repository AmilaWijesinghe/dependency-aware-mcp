"""Test-only MongoDB/model substitutes. MCP, OCC and graph services stay real."""

import json
import re
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import httpx2
from fastmcp.client.transports import StreamableHttpTransport
from langchain_core.messages import AIMessage

from app.mcp_client import traced_tools
from app.mcp_server.server import mcp
from app.schemas.conflict import SemanticConflictDecision
from app.schemas.recovery import RecoveryDecision


def matches(document, query):
    for key, value in query.items():
        if isinstance(value, dict) and "$lte" in value:
            if document.get(key) > value["$lte"]:
                return False
        elif document.get(key) != value:
            return False
    return True


class Cursor:
    def __init__(self, documents):
        self.documents = deepcopy(documents)

    def sort(self, key, direction):
        self.documents.sort(key=lambda document: document[key], reverse=direction < 0)
        return self

    async def to_list(self, length=None):
        return deepcopy(self.documents[:length])


class Collection:
    def __init__(self):
        self.documents = []

    async def insert_one(self, document):
        document = deepcopy(document)
        document.setdefault("_id", str(len(self.documents)))
        assert not any(item["_id"] == document["_id"] for item in self.documents)
        self.documents.append(document)
        return SimpleNamespace(inserted_id=document["_id"])

    def find(self, query):
        return Cursor([item for item in self.documents if matches(item, query)])

    async def find_one(self, query, sort=None):
        cursor = self.find(query)
        for key, direction in reversed(sort or []):
            cursor.sort(key, direction)
        return next(iter(await cursor.to_list(1)), None)

    async def find_one_and_update(self, query, update, **kwargs):
        for document in self.documents:
            if matches(document, query):
                document.update(deepcopy(update.get("$set", {})))
                for key, increment in update.get("$inc", {}).items():
                    document[key] += increment
                return deepcopy(document)
        return None

    async def update_one(self, query, update):
        return await self.find_one_and_update(query, update)

    async def count_documents(self, query):
        return len([item for item in self.documents if matches(item, query)])


def controlled_worker(*, name, tools):
    """Replace only model invocation; execute the actual LangChain MCP tools."""
    async def ainvoke(inputs):
        prompt = inputs["messages"][0]["content"]
        key = re.search(r"demo/[\w-]+/product_1", prompt).group()
        tool = tools[0]
        arguments = {"resource_key": key}
        if tool.name == "write_shared_resource":
            arguments.update(
                new_value=json.loads(prompt[prompt.index("{"):prompt.rindex("}") + 1]),
                expected_version=int(re.search(r"expected_version:\s*(\d+)", prompt).group(1)),
            )
        await tool.ainvoke(arguments)
        return {"messages": [AIMessage(content="PRIVATE_MODEL_TEXT_MUST_NOT_STREAM")]}
    return SimpleNamespace(ainvoke=ainvoke)


async def controlled_classify(self, **evidence):
    disruptive = "independent" not in evidence["worker_purpose"]
    return SemanticConflictDecision(
        semantic_result="disruptive" if disruptive else "non_disruptive",
        affected_premises=["current quantity"] if disruptive else [],
        reason="The quantity premise changed." if disruptive else "The price decision is independent of quantity.",
        confidence=0.9,
    )


async def controlled_plan(self, *, worker_purpose, current_state):
    return RecoveryDecision(action="write", new_value={**current_state, "quantity": current_state["quantity"] - 30}, reason="Allocation recalculated.", confidence=0.9)


class IsolatedResearchStack:
    async def __aenter__(self):
        self.collections = {name: Collection() for name in [
            "resources", "access_logs", "conflicts", "dependencies", "node_executions",
        ]}
        self.app = mcp.streamable_http_app(stateless_http=True, json_response=True)
        self.patches = []
        for module, names in [
            ("app.concurrency.middleware", ["resources"]),
            ("app.storage.repositories", ["access_logs", "conflicts", "dependencies", "node_executions"]),
            ("app.demo.service", ["resources", "access_logs", "conflicts"]),
        ]:
            for name in names:
                self.patches.append(patch(f"{module}.{name}", self.collections[name]))

        def transport(*args, **kwargs):
            return StreamableHttpTransport(*args, **kwargs, httpx_client_factory=lambda **options:
                httpx2.AsyncClient(**options, transport=httpx2.ASGITransport(app=self.app)))

        self.patches.extend([
            patch.object(traced_tools, "StreamableHttpTransport", transport),
            patch("app.graph.phase4.create_worker", controlled_worker),
            patch("app.agents.auditor.SemanticAuditor.classify", controlled_classify),
            patch("app.agents.recovery_planner.RecoveryPlanner.plan", controlled_plan),
        ])
        for patcher in self.patches:
            patcher.start()
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        return self

    async def __aexit__(self, *exc):
        try:
            await self.lifespan.__aexit__(*exc)
        finally:
            for patcher in reversed(self.patches):
                patcher.stop()
