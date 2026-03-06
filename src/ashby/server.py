# /// script
# dependencies = [
#   "mcp",
#   "requests",
#   "python-dotenv"
# ]
# ///
import asyncio
import base64
import json
from typing import Any, Optional
import os
from dotenv import load_dotenv
import requests

import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio

"""
Ashby MCP Server - Model Context Protocol server for Ashby ATS integration.

This server provides READ-ONLY tools to query the Ashby API. All endpoints
have been verified against the official Ashby API documentation. No action
endpoints (create, update, delete, schedule) are exposed.

## Tool Categories

- **Candidate Discovery & Details**: Search/list candidates, view profiles, resumes, notes
- **Application Tracking**: List/inspect applications, history, feedback/scorecards
- **Job & Opening Intelligence**: Search/list jobs, inspect openings for headcount tracking
- **Interview Intelligence**: View interview schedules, events, stages, and plans
- **Offers & Organization**: Track offers, view department structure

## Key Concepts

- **Candidate ID vs Application ID**: Candidate-level tools require a `candidate_id`,
  application-level tools require an `application_id`. Use `get_candidate_info` to
  retrieve a candidate's `applicationIds` to bridge between them.
- **Jobs vs Openings**: A Job is a role being hired for. An Opening represents a
  specific headcount slot within a job (e.g., "3 openings for Software Engineer").
  Use openings to answer "are we ahead or behind plan?" questions.
- **Interview Plans vs Stages vs Schedules vs Events**: An interview plan defines
  the process for a job. Stages are steps within a plan. Schedules are actual
  scheduled interview sessions. Events are individual calendar events within a schedule.

## Common Workflows

1. **"How many candidates for this role?"**:
   search_jobs → list_applications (filter by jobId)

2. **"Anyone at the final stage?"**:
   list_applications (filter by jobId) → get_application_info (check currentInterviewStage)

3. **"What happened to this candidate?"**:
   search_candidates → get_candidate_info → get_application_history

4. **"When is someone being interviewed next?"**:
   get_application_info → list_interview_schedules (filter by applicationId)
   → list_interview_events

5. **"Are we ahead or behind plan?"**:
   list_jobs (filter by status) → list_openings (check openingState: Open vs Filled)

6. **"How many hires in Q1?"**:
   list_applications (filter by status=Hired, createdAfter/before dates)

## API Limitations

- Email and SMS communication history are not available via API
- File download URLs from `get_resume_url` may expire
- Pagination uses cursor-based pagination (max 100 results per page)
"""

class AshbyClient:
    """Handles Ashby operations and caching."""

    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url = "https://api.ashbyhq.com"
        self.headers = {}

    def connect(self) -> bool:
        try:
            self.api_key = os.getenv('ASHBY_API_KEY')
            if not self.api_key:
                raise ValueError("ASHBY_API_KEY environment variable not set")

            credentials = base64.b64encode(f"{self.api_key}:".encode()).decode()
            self.headers = {
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json"
            }
            return True
        except Exception as e:
            print(f"Ashby connection failed: {str(e)}")
            return False

    def _make_request(self, endpoint: str, data: Optional[dict] = None) -> dict:
        if not self.api_key:
            raise ValueError("Ashby connection not established")

        url = f"{self.base_url}{endpoint}"
        response = requests.post(
            url=url,
            headers=self.headers,
            json=data or {}
        )
        response.raise_for_status()
        return response.json()

# Create a server instance
server = Server("ashby-mcp")

# Load environment variables
load_dotenv()

# Configure with Ashby API key from environment variables
ashby_client = AshbyClient()
if not ashby_client.connect():
    print("Failed to initialize Ashby connection")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        # ── Candidate Discovery & Details ──────────────────────────────

        types.Tool(
            name="search_candidates",
            description="Search for candidates by email and/or name. Returns matching candidate records.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Candidate's email address"},
                    "name": {"type": "string", "description": "Candidate's name"}
                }
            }
        ),
        types.Tool(
            name="list_candidates",
            description="List all candidates with cursor-based pagination. Returns up to 100 candidates per page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cursor": {"type": "string", "description": "Opaque cursor from a previous response for pagination"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100},
                    "syncToken": {"type": "string", "description": "Token for incremental sync to only get changes since last call"}
                }
            }
        ),
        types.Tool(
            name="get_candidate_info",
            description="Get detailed information about a specific candidate including name, email, phone, LinkedIn, resume file handle, application IDs, tags, and custom fields.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The candidate's UUID"}
                },
                "required": ["id"]
            }
        ),
        types.Tool(
            name="get_resume_url",
            description="Get a downloadable URL for a candidate's resume file. Use the file handle from the candidate's resumeFileHandle.handle field.",
            inputSchema={
                "type": "object",
                "properties": {
                    "fileHandle": {"type": "string", "description": "The file handle from candidate's resumeFileHandle.handle field"}
                },
                "required": ["fileHandle"]
            }
        ),
        types.Tool(
            name="list_candidate_notes",
            description="List all notes on a candidate's profile.",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidateId": {"type": "string", "description": "The candidate's UUID"},
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100}
                },
                "required": ["candidateId"]
            }
        ),

        # ── Application Tracking ───────────────────────────────────────

        types.Tool(
            name="list_applications",
            description="List all applications with filtering. Filter by status (Hired/Archived/Active/Lead) and jobId to answer questions like 'how many candidates for this role?' or 'how many hires this quarter?'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100},
                    "syncToken": {"type": "string", "description": "Token for incremental sync"},
                    "createdAfter": {"type": "integer", "description": "Only return applications created after this timestamp (Unix epoch milliseconds)"},
                    "status": {
                        "type": "string",
                        "description": "Filter by status",
                        "enum": ["Hired", "Archived", "Active", "Lead"]
                    },
                    "jobId": {"type": "string", "description": "Filter by job UUID"},
                    "expand": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["openings"]},
                        "description": "Expand related objects inline"
                    }
                }
            }
        ),
        types.Tool(
            name="get_application_info",
            description="Get detailed information about a specific application including its current interview stage, status (Hired/Archived/Active/Lead), candidate info, job info, source, archive reason, and hiring team.",
            inputSchema={
                "type": "object",
                "properties": {
                    "applicationId": {"type": "string", "description": "The application UUID"},
                    "expand": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["openings", "applicationFormSubmissions", "referrals"]},
                        "description": "Expand related objects inline"
                    }
                },
                "required": ["applicationId"]
            }
        ),
        types.Tool(
            name="get_application_history",
            description="Get the activity timeline and stage changes for an application. Shows when a candidate moved between stages, received feedback, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "applicationId": {"type": "string", "description": "The application UUID"},
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100}
                },
                "required": ["applicationId"]
            }
        ),
        types.Tool(
            name="get_application_feedback",
            description="Get interview feedback and scorecards for an application. Can also list all feedback org-wide when no applicationId is provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "applicationId": {"type": "string", "description": "Filter feedback to a specific application UUID"},
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100},
                    "syncToken": {"type": "string", "description": "Token for incremental sync"},
                    "createdAfter": {"type": "integer", "description": "Only return feedback created after this timestamp (Unix epoch milliseconds)"}
                }
            }
        ),

        # ── Job & Opening Intelligence ─────────────────────────────────

        types.Tool(
            name="search_jobs",
            description="Search for jobs by title. Returns matching job records.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Job title to search for"}
                }
            }
        ),
        types.Tool(
            name="list_jobs",
            description="List all jobs with optional status and date filters. Use this to answer 'how many open roles are there?' by filtering status=['Open'].",
            inputSchema={
                "type": "object",
                "properties": {
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100},
                    "syncToken": {"type": "string", "description": "Token for incremental sync"},
                    "status": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["Draft", "Open", "Closed", "Archived"]},
                        "description": "Filter by job status(es)"
                    },
                    "openedAfter": {"type": "integer", "description": "Jobs opened after this timestamp (Unix epoch ms)"},
                    "openedBefore": {"type": "integer", "description": "Jobs opened before this timestamp (Unix epoch ms)"},
                    "closedAfter": {"type": "integer", "description": "Jobs closed after this timestamp (Unix epoch ms)"},
                    "closedBefore": {"type": "integer", "description": "Jobs closed before this timestamp (Unix epoch ms)"},
                    "expand": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["location", "openings"]},
                        "description": "Expand related objects inline"
                    }
                }
            }
        ),
        types.Tool(
            name="get_job_info",
            description="Get detailed information about a specific job including title, status, department, location, custom fields, and optionally its openings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The job UUID"},
                    "expand": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["location", "openings"]},
                        "description": "Expand related objects inline"
                    }
                },
                "required": ["id"]
            }
        ),
        types.Tool(
            name="list_openings",
            description="List all openings (headcount slots). Each opening has an openingState (Approved/Open/Closed/Draft/Filled). Use this to track headcount: compare Open vs Filled openings to see if hiring is ahead or behind plan.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "syncToken": {"type": "string", "description": "Token for incremental sync"}
                }
            }
        ),
        types.Tool(
            name="get_opening_info",
            description="Get details about a specific opening (headcount slot) including its state, associated jobs, locations, and hiring team.",
            inputSchema={
                "type": "object",
                "properties": {
                    "openingId": {"type": "string", "description": "The opening UUID"}
                },
                "required": ["openingId"]
            }
        ),

        # ── Interview Intelligence ─────────────────────────────────────

        types.Tool(
            name="list_interviews",
            description="List all interviews in the organization with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100},
                    "syncToken": {"type": "string", "description": "Token for incremental sync"}
                }
            }
        ),
        types.Tool(
            name="get_interview_info",
            description="Get details about a specific interview by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The interview UUID"}
                },
                "required": ["id"]
            }
        ),
        types.Tool(
            name="list_interview_schedules",
            description="List interview schedules. Filter by applicationId to find when a specific candidate is being interviewed next, or by interviewStageId to see all schedules for a particular stage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100},
                    "syncToken": {"type": "string", "description": "Token for incremental sync"},
                    "createdAfter": {"type": "integer", "description": "Only return schedules created after this timestamp (Unix epoch ms)"},
                    "applicationId": {"type": "string", "description": "Filter by application UUID"},
                    "interviewStageId": {"type": "string", "description": "Filter by interview stage UUID"}
                }
            }
        ),
        types.Tool(
            name="list_interview_events",
            description="List interview events (individual calendar events) for a specific interview schedule. Use this to find exact interview times, interviewers, and locations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "interviewScheduleId": {"type": "string", "description": "The interview schedule UUID to list events for"},
                    "expand": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["interview"]},
                        "description": "Expand the interview object inline"
                    }
                },
                "required": ["interviewScheduleId"]
            }
        ),
        types.Tool(
            name="list_interview_stages",
            description="List all interview stages for a given interview plan, in order. Shows the sequence of stages candidates go through (e.g., Phone Screen → Technical → Onsite → Offer).",
            inputSchema={
                "type": "object",
                "properties": {
                    "interviewPlanId": {"type": "string", "description": "The interview plan UUID to list stages for"}
                },
                "required": ["interviewPlanId"]
            }
        ),
        types.Tool(
            name="list_interview_plans",
            description="List all interview plans. An interview plan defines the stages and process for hiring for a job.",
            inputSchema={
                "type": "object",
                "properties": {
                    "includeArchived": {"type": "boolean", "description": "Include archived plans (default: false)"}
                }
            }
        ),

        # ── Offers & Organization ──────────────────────────────────────

        types.Tool(
            name="list_offers",
            description="List all offers with their latest version. Filter by applicationId to see offers for a specific candidate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                    "limit": {"type": "integer", "description": "Max results to return (max 100)", "default": 100},
                    "syncToken": {"type": "string", "description": "Token for incremental sync"},
                    "applicationId": {"type": "string", "description": "Filter by application UUID"}
                }
            }
        ),
        types.Tool(
            name="get_offer_info",
            description="Get details about a specific offer including compensation, status, and approval state.",
            inputSchema={
                "type": "object",
                "properties": {
                    "offerId": {"type": "string", "description": "The offer UUID"}
                },
                "required": ["offerId"]
            }
        ),
        types.Tool(
            name="list_departments",
            description="List all departments in the organization. Useful for understanding org structure and filtering jobs/candidates by department.",
            inputSchema={
                "type": "object",
                "properties": {
                    "includeArchived": {"type": "boolean", "description": "Include archived departments (default: false)"}
                }
            }
        ),
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls by routing to the verified Ashby API endpoints."""
    try:
        # ── Candidate Discovery & Details ──────────────────────────
        if name == "search_candidates":
            filtered_args = {k: v for k, v in arguments.items() if v}
            response = ashby_client._make_request("/candidate.search", data=filtered_args)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_candidates":
            response = ashby_client._make_request("/candidate.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_candidate_info":
            response = ashby_client._make_request("/candidate.info", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_resume_url":
            response = ashby_client._make_request("/file.info", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_candidate_notes":
            response = ashby_client._make_request("/candidate.listNotes", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        # ── Application Tracking ──────────────────────────────────
        elif name == "list_applications":
            response = ashby_client._make_request("/application.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_application_info":
            response = ashby_client._make_request("/application.info", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_application_history":
            response = ashby_client._make_request("/application.listHistory", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_application_feedback":
            response = ashby_client._make_request("/applicationFeedback.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        # ── Job & Opening Intelligence ────────────────────────────
        elif name == "search_jobs":
            response = ashby_client._make_request("/job.search", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_jobs":
            response = ashby_client._make_request("/job.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_job_info":
            response = ashby_client._make_request("/job.info", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_openings":
            response = ashby_client._make_request("/opening.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_opening_info":
            response = ashby_client._make_request("/opening.info", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        # ── Interview Intelligence ────────────────────────────────
        elif name == "list_interviews":
            response = ashby_client._make_request("/interview.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_interview_info":
            response = ashby_client._make_request("/interview.info", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_interview_schedules":
            response = ashby_client._make_request("/interviewSchedule.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_interview_events":
            response = ashby_client._make_request("/interviewEvent.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_interview_stages":
            response = ashby_client._make_request("/interviewStage.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_interview_plans":
            response = ashby_client._make_request("/interviewPlan.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        # ── Offers & Organization ─────────────────────────────────
        elif name == "list_offers":
            response = ashby_client._make_request("/offer.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "get_offer_info":
            response = ashby_client._make_request("/offer.info", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        elif name == "list_departments":
            response = ashby_client._make_request("/department.list", data=arguments)
            return [types.TextContent(type="text", text=json.dumps(response, indent=2))]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error executing {name}: {str(e)}")]

async def run():
    """Run the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ashby",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(run())
