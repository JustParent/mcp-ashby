import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def spec() -> dict:
    """The official Ashby OpenAPI spec, vendored at the repo root."""
    return json.loads((ROOT / "openapi.json").read_text())


def resolve(ref: str, root: dict):
    """Resolve a JSON-Pointer $ref against the spec root."""
    cur = root
    for seg in ref.lstrip("#/").split("/"):
        seg = seg.replace("~1", "/").replace("~0", "~")
        cur = cur[int(seg)] if isinstance(cur, list) else cur[seg]
    return cur


def request_properties(endpoint: str, root: dict, _depth: int = 0) -> set[str]:
    """Every accepted request-body property for an endpoint, flattening allOf and $ref."""
    schema = (
        root["paths"][endpoint]["post"]
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    return _props(schema, root)


def _props(node, root, depth=0) -> set[str]:
    if depth > 10 or not isinstance(node, dict):
        return set()
    found = set(node.get("properties", {}).keys())
    if "$ref" in node:
        found |= _props(resolve(node["$ref"], root), root, depth + 1)
    for branch in node.get("allOf", []) + node.get("oneOf", []) + node.get("anyOf", []):
        found |= _props(branch, root, depth + 1)
    return found


def required_properties(endpoint: str, root: dict) -> set[str]:
    schema = (
        root["paths"][endpoint]["post"]
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    return set(schema.get("required", []))
