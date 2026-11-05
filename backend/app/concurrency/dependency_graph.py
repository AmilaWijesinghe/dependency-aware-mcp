import networkx as nx

from app.storage.repositories import (
    DependencyRepository,
)

# These are worker-level dependency edges for
# the Phase 4 experiment.
#
# A's stale commit depends on A's original read.
#
# B's commit depends on B's original read.
WORKFLOW_EDGES = [
    (
        "a_read",
        "a_stale_write",
    ),
    (
        "b_read",
        "b_write",
    ),
]


WORKER_NODES = {
    "a_read",
    "a_stale_write",
    "b_read",
    "b_write",
}


class DependencyGraphService:

    def __init__(self) -> None:
        self.repository = DependencyRepository()

    async def build_graph(
        self,
        *,
        run_id: str,
    ) -> nx.DiGraph:

        graph = nx.DiGraph()

        dependency_docs = await self.repository.get_run_dependencies(run_id=run_id)

        # ---------------------------------------------
        # Resource-version → node edges
        # ---------------------------------------------

        for dependency in dependency_docs:

            resource_node = (
                f"resource:"
                f'{dependency["resourceKey"]}'
                f':v{dependency["readVersion"]}'
            )

            execution_node = dependency["nodeId"]

            graph.add_node(
                resource_node,
                node_type="resource_version",
            )

            graph.add_node(
                execution_node,
                node_type="execution",
                agent_id=dependency["agentId"],
            )

            graph.add_edge(
                resource_node,
                execution_node,
                edge_type="read_dependency",
            )

        # ---------------------------------------------
        # Execution → execution edges
        # ---------------------------------------------

        for source, target in WORKFLOW_EDGES:

            graph.add_node(
                source,
                node_type="execution",
            )

            graph.add_node(
                target,
                node_type="execution",
            )

            graph.add_edge(
                source,
                target,
                edge_type="workflow_dependency",
            )

        return graph

    async def find_affected_nodes(
        self,
        *,
        run_id: str,
        agent_id: str,
        resource_key: str,
        stale_version: int,
    ) -> tuple[list[str], list[str]]:

        graph = await self.build_graph(run_id=run_id)

        dependency_docs = await self.repository.get_run_dependencies(run_id=run_id)

        starting_nodes = {
            item["nodeId"]
            for item in dependency_docs
            if (
                item["agentId"] == agent_id
                and item["resourceKey"] == resource_key
                and item["readVersion"] == stale_version
            )
        }

        affected: set[str] = set()

        for node_id in starting_nodes:

            affected.add(node_id)

            affected.update(
                nx.descendants(
                    graph,
                    node_id,
                )
            )

        # Only worker execution nodes matter for
        # selective recovery.
        affected &= WORKER_NODES

        preserved = WORKER_NODES - affected

        return (
            sorted(affected),
            sorted(preserved),
        )
