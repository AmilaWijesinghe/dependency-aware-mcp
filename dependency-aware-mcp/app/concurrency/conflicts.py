"""Domain exceptions remain typed until the MCP boundary."""

from app.schemas.conflict import ConflictResult


class ResourceNotFound(Exception):
    def __init__(self, resource_key: str):
        self.resource_key = resource_key
        super().__init__(f"Resource not found: {resource_key}")


class VersionConflict(Exception):
    def __init__(
        self,
        resource_key: str,
        expected_version: int,
        actual_version: int | None = None,
    ):
        self.resource_key = resource_key
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"VERSION CONFLICT {resource_key}: "
            f"expected={expected_version}, actual={actual_version}"
        )

    def as_result(self) -> ConflictResult:
        return ConflictResult(
            resource_key=self.resource_key,
            expected_version=self.expected_version,
            current_version=self.actual_version,
        )


class MissingExecutionContext(Exception):
    """A tool call has no complete runtime-supplied provenance identity."""
