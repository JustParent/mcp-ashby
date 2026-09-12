"""Offline contract tests: every MCP tool is checked against the vendored
official Ashby OpenAPI spec. These run with no network and no API key, and
deterministically catch hallucinated endpoints or parameters.
"""
import asyncio

import pytest

from conftest import request_properties, required_properties
from src.ashby import server

# Tool name -> Ashby endpoint it must route to.
EXPECTED_ROUTES = {
    "search_candidates": "/candidate.search",
    "list_candidates": "/candidate.list",
    "get_candidate_info": "/candidate.info",
    "get_resume_url": "/file.info",
    "list_candidate_notes": "/candidate.listNotes",
    "list_applications": "/application.list",
    "get_application_info": "/application.info",
    "get_application_history": "/application.listHistory",
    "get_application_feedback": "/applicationFeedback.list",
    "search_jobs": "/job.search",
    "list_jobs": "/job.list",
    "get_job_info": "/job.info",
    "list_openings": "/opening.list",
    "get_opening_info": "/opening.info",
    "search_openings": "/opening.search",
    "list_custom_fields": "/customField.list",
    "list_interviews": "/interview.list",
    "get_interview_info": "/interview.info",
    "list_interview_schedules": "/interviewSchedule.list",
    "list_interview_events": "/interviewEvent.list",
    "list_interview_stages": "/interviewStage.list",
    "list_interview_plans": "/interviewPlan.list",
    "list_offers": "/offer.list",
    "get_offer_info": "/offer.info",
    "list_departments": "/department.list",
}

WRITE_VERBS = (
    "create", "update", "delete", "archive", "restore", "move", "set",
    "add", "remove", "schedule", "submit", "publish", "unpublish", "upload",
)


def tools():
    return asyncio.run(server.handle_list_tools())


def route_for(tool_name: str, args: dict) -> tuple[str, dict]:
    """Invoke the real routing code with a fake transport; return (endpoint, payload)."""
    captured = {}

    def fake_request(endpoint, data=None):
        captured["endpoint"] = endpoint
        captured["data"] = data
        return {"success": True, "results": []}

    original = server.ashby_client._make_request
    server.ashby_client._make_request = fake_request
    try:
        asyncio.run(server.handle_call_tool(tool_name, args))
    finally:
        server.ashby_client._make_request = original
    return captured.get("endpoint"), captured.get("data")


# ── Regression guards over the whole tool surface ──────────────────────

def test_every_tool_routes_to_an_endpoint_that_exists_in_the_spec(spec):
    for name, endpoint in EXPECTED_ROUTES.items():
        assert endpoint in spec["paths"], f"{name} -> {endpoint} is not a real Ashby endpoint"


def test_every_exposed_tool_has_an_expected_route():
    exposed = {t.name for t in tools()}
    assert exposed == set(EXPECTED_ROUTES), (
        f"missing={set(EXPECTED_ROUTES) - exposed} unexpected={exposed - set(EXPECTED_ROUTES)}"
    )


def test_no_tool_exposes_a_write_endpoint():
    for name, endpoint in EXPECTED_ROUTES.items():
        action = endpoint.split(".", 1)[1]
        assert not action.startswith(WRITE_VERBS), f"{name} -> {endpoint} is not read-only"


def test_every_tool_parameter_is_accepted_by_its_endpoint(spec):
    for tool in tools():
        endpoint = EXPECTED_ROUTES[tool.name]
        declared = set(tool.inputSchema.get("properties", {}).keys())
        accepted = request_properties(endpoint, spec)
        assert declared <= accepted, (
            f"{tool.name} declares {declared - accepted} which {endpoint} does not accept"
        )


def test_every_tool_declares_the_parameters_its_endpoint_requires(spec):
    for tool in tools():
        endpoint = EXPECTED_ROUTES[tool.name]
        declared_required = set(tool.inputSchema.get("required", []))
        spec_required = required_properties(endpoint, spec)
        assert spec_required <= declared_required, (
            f"{tool.name} omits required param(s) {spec_required - declared_required} for {endpoint}"
        )


@pytest.mark.parametrize("name,endpoint", sorted(EXPECTED_ROUTES.items()))
def test_tool_routes_to_its_declared_endpoint(name, endpoint):
    tool = next(t for t in tools() if t.name == name)
    args = {p: "probe" for p in tool.inputSchema.get("required", [])}
    assert route_for(name, args)[0] == endpoint


# ── The two tools that close the HiBob cross-reference gaps ────────────

def test_search_openings_looks_up_an_opening_by_hibob_identifier():
    endpoint, payload = route_for("search_openings", {"identifier": "O-342524"})
    assert endpoint == "/opening.search"
    assert payload == {"identifier": "O-342524"}


def test_list_custom_fields_can_discover_opening_field_definitions():
    endpoint, payload = route_for("list_custom_fields", {"includeArchived": True})
    assert endpoint == "/customField.list"
    assert payload == {"includeArchived": True}


def test_new_tools_drop_empty_arguments_that_ashby_rejects():
    """Ashby returns invalid_input for empty-string params (cf. commit 3c0e651)."""
    assert route_for("search_openings", {"identifier": "O-1", "cursor": ""})[1] == {"identifier": "O-1"}
    assert route_for("list_custom_fields", {"cursor": ""})[1] == {}
