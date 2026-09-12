"""Minimal stub of the Ashby API serving spec-shaped fixtures, to verify the
live test suite's logic without a real key. HIBOB=0 strips the HiBob fields.
"""
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

HIBOB = os.getenv("HIBOB", "1") == "1"

OPENING_CF = ([{"id": "cf1", "isPrivate": False, "title": "WFP Opening ID", "value": "O-342524"},
               {"id": "cf2", "isPrivate": False, "title": "HiBob Position ID", "value": "P-53902"}]
              if HIBOB else
              [{"id": "cf3", "isPrivate": False, "title": "Cost Centre", "value": "CC-9"}])

CUSTOM_FIELDS = [
    {"id": "cf1", "title": "WFP Opening ID" if HIBOB else "Cost Centre",
     "objectType": "Opening", "isArchived": False, "fieldType": "String", "isPrivate": False},
    {"id": "cf2", "title": "HiBob Position ID" if HIBOB else "Team Code",
     "objectType": "Opening", "isArchived": False, "fieldType": "String", "isPrivate": False},
    {"id": "cf9", "title": "Referral Source", "objectType": "Candidate",
     "isArchived": False, "fieldType": "String", "isPrivate": False},
]

OPENINGS = [{
    "id": "11111111-1111-1111-1111-111111111111",
    "openingState": "Open", "isArchived": False,
    "latestVersion": {
        "id": "v1", "identifier": "O-342524" if HIBOB else "REQ-1",
        "description": "", "authorId": "u1", "createdAt": "2026-01-01T00:00:00Z",
        "jobIds": ["22222222-2222-2222-2222-222222222222"],
        "isBackfill": False, "employmentType": "FullTime",
        "locationIds": [], "hiringTeam": [], "customFields": OPENING_CF,
    },
}]

ROUTES = {
    "/apiKey.info": {"success": True, "results": {"id": "k1"}},
    "/candidate.list": {"success": True, "results": [], "moreDataAvailable": False},
    "/application.list": {"success": True, "results": [], "moreDataAvailable": False},
    "/job.list": {"success": True, "results": [{"id": "22222222-2222-2222-2222-222222222222"}],
                  "moreDataAvailable": False},
    "/job.search": {"success": True, "results": []},
    "/opening.list": {"success": True, "results": OPENINGS, "moreDataAvailable": False},
    "/opening.search": {"success": True, "results": OPENINGS},
    "/customField.list": {"success": True, "results": CUSTOM_FIELDS, "moreDataAvailable": False},
    "/interview.list": {"success": True, "results": [], "moreDataAvailable": False},
    "/interviewSchedule.list": {"success": True, "results": [], "moreDataAvailable": False},
    "/interviewPlan.list": {"success": True, "results": []},
    "/offer.list": {"success": True, "results": [], "moreDataAvailable": False},
    "/department.list": {"success": True, "results": []},
    "/job.info": {"success": True, "results": {"id": "22222222-2222-2222-2222-222222222222",
                                               "title": "Engineer", "status": "Open",
                                               "customFields": [], "openings": OPENINGS}},
}

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        body = ROUTES.get(self.path, {"success": False, "errors": ["not_stubbed"]})
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
