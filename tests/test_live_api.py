"""Live integration tests against the real Ashby API.

These auto-skip when ASHBY_API_KEY is missing or rejected, so `pytest tests/`
is always safe to run. The moment a working key is in .env they execute for
real and validate the HiBob Workforce Planning cross-reference end to end.
"""
import base64
import json
import os
import re

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()

# Overridable so the suite can be exercised against a stub (see tests/stub_ashby.py).
BASE = os.getenv("ASHBY_API_BASE", "https://api.ashbyhq.com")
KEY = os.getenv("ASHBY_API_KEY")

# HiBob WFP identifiers: opening IDs like O-342524, position IDs like P-53902.
HIBOB_ID = re.compile(r"\b([OP]-\d{4,})\b")
HIBOB_TITLE = re.compile(r"hibob|bob|wfp|workforce|position\s*id|opening\s*id", re.I)

READ_ONLY_ENDPOINTS = [
    ("/candidate.list", {"limit": 1}),
    ("/application.list", {"limit": 1}),
    ("/job.list", {"limit": 1}),
    ("/job.search", {"title": "e"}),
    ("/opening.list", {}),
    ("/customField.list", {}),
    ("/interview.list", {"limit": 1}),
    ("/interviewSchedule.list", {"limit": 1}),
    ("/interviewPlan.list", {}),
    ("/offer.list", {"limit": 1}),
    ("/department.list", {}),
]


def call(endpoint, data=None):
    headers = {
        "Authorization": "Basic " + base64.b64encode(f"{KEY}:".encode()).decode(),
        "Content-Type": "application/json",
    }
    return requests.post(BASE + endpoint, headers=headers, json=data or {}, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def require_working_key():
    if not KEY:
        pytest.skip("ASHBY_API_KEY not set", allow_module_level=True)
    r = call("/apiKey.info")
    if r.status_code == 401:
        pytest.skip(
            "ASHBY_API_KEY rejected by Ashby (HTTP 401). A valid key lacking "
            "permissions returns HTTP 200 with success=false, so this key is "
            "invalid or revoked -- replace it in .env to run live tests.",
            allow_module_level=True,
        )


@pytest.fixture(scope="session")
def openings():
    results, cursor = [], None
    for _ in range(50):
        body = call("/opening.list", {"cursor": cursor} if cursor else {}).json()
        assert body.get("success"), body
        results.extend(body["results"])
        if not body.get("moreDataAvailable"):
            break
        cursor = body.get("nextCursor")
    return results


@pytest.fixture(scope="session")
def custom_fields():
    body = call("/customField.list").json()
    assert body.get("success"), body
    return body["results"]


@pytest.mark.parametrize("endpoint,payload", READ_ONLY_ENDPOINTS)
def test_endpoint_returns_success(endpoint, payload):
    r = call(endpoint, payload)
    assert r.status_code == 200, f"{endpoint} -> HTTP {r.status_code}: {r.text[:200]}"
    assert r.json().get("success") is True, f"{endpoint} -> {r.text[:300]}"


def test_an_opening_scoped_custom_field_is_configured(custom_fields):
    opening_fields = [f for f in custom_fields if f.get("objectType") == "Opening"]
    assert opening_fields, (
        "No Opening-scoped custom fields exist in Ashby. The HiBob WFP mapping "
        "depends on opening custom fields. Configured objectTypes: "
        f"{sorted({f.get('objectType') for f in custom_fields})}"
    )


def test_hibob_identifier_fields_are_named_on_openings_or_jobs(custom_fields):
    named = [
        f"{f.get('objectType')}.{f.get('title')}"
        for f in custom_fields
        if f.get("objectType") in ("Opening", "Job") and HIBOB_TITLE.search(f.get("title", ""))
    ]
    assert named, (
        "No Opening/Job custom field title mentions HiBob/WFP/position/opening ID. "
        "Titles present: "
        + json.dumps([f"{f.get('objectType')}.{f.get('title')}" for f in custom_fields
                      if f.get("objectType") in ("Opening", "Job")])
    )


def test_openings_expose_hibob_identifiers(openings):
    """The crux: O-###### / P-##### must be readable off an opening."""
    assert openings, "Ashby returned zero openings"
    found = {}
    for o in openings:
        version = o.get("latestVersion") or {}
        for match in HIBOB_ID.findall(json.dumps(version)):
            found.setdefault(match, o.get("id"))
    assert found, (
        "No HiBob-shaped identifiers (O-###### / P-#####) found on any of "
        f"{len(openings)} openings. Custom field titles populated on openings: "
        + json.dumps(sorted({
            c.get("title")
            for o in openings
            for c in (o.get("latestVersion") or {}).get("customFields", [])
        }))
    )


def test_opening_carries_its_state_and_linked_jobs(openings):
    """Q6: opening status plus the corresponding Ashby job."""
    assert openings
    states = {"Approved", "Closed", "Draft", "Filled", "Open"}
    for o in openings:
        assert o.get("openingState") in states, o
    linked = [o for o in openings if (o.get("latestVersion") or {}).get("jobIds")]
    assert linked, "No opening is linked to an Ashby job via latestVersion.jobIds"


def test_opening_search_resolves_an_identifier(openings):
    """The reverse lookup search_openings depends on."""
    identifier = next(
        (o["latestVersion"]["identifier"]
         for o in openings
         if (o.get("latestVersion") or {}).get("identifier")),
        None,
    )
    if not identifier:
        pytest.skip("no opening carries an identifier to probe")
    body = call("/opening.search", {"identifier": identifier}).json()
    assert body.get("success"), body
    assert body["results"], f"opening.search found nothing for {identifier!r}"


def test_job_expands_its_openings():
    jobs = call("/job.list", {"limit": 1}).json()
    assert jobs.get("success"), jobs
    if not jobs["results"]:
        pytest.skip("no jobs in this Ashby workspace")
    job_id = jobs["results"][0]["id"]
    body = call("/job.info", {"id": job_id, "expand": ["openings"]}).json()
    assert body.get("success"), body
    assert "openings" in body["results"], "job.info did not honour expand=[openings]"
