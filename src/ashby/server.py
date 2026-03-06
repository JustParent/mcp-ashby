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

This server provides tools to interact with the Ashby API including:
- Candidate management (create, search, list, get detailed info)
- Resume/file access
- Notes (list and create)
- Application history and activity timeline
- Interview feedback and scorecards
- Job management
- Interview scheduling
- Analytics

## Important Distinctions

**Candidate ID vs Application ID**:
- Candidate-level tools (get_candidate_info, list_candidate_notes, create_candidate_note)
  require a `candidate_id`
- Application-level tools (get_application_history, get_application_feedback)
  require an `application_id`
- Use `get_candidate_info` to retrieve a candidate's `applicationIds` to bridge between them

## API Limitations

**Not Available via API** (visible in Ashby UI only):
- Email communication history
- SMS/text message history

**Other Notes**:
- File download URLs from `get_resume_url` may expire over time
- Some endpoints require specific Ashby API permissions (candidatesRead, candidatesWrite)

## Example Workflows

1. **Get candidate's LinkedIn and resume**:
   search_candidates → get_candidate_info → get_resume_url

2. **View and add notes**:
   get_candidate_info → list_candidate_notes → create_candidate_note

3. **Review application progress**:
   get_candidate_info → get_application_history → get_application_feedback
"""

class AshbyClient:
    """Handles Ashby operations and caching."""
    
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url = "https://api.ashbyhq.com"
        self.headers = {}

    def connect(self) -> bool:
        """Establishes connection to Ashby using API key from environment variables.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
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

    def _make_request(self, endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
        """Make a request to the Ashby API.
        
        Args:
            endpoint (str): The API endpoint to call
            method (str): HTTP method (GET, POST, etc.)
            data (Optional[dict]): Data to send with the request
            
        Returns:
            dict: Response from the API
        """
        if not self.api_key:
            raise ValueError("Ashby connection not established")
            
        url = f"{self.base_url}{endpoint}"
        response = requests.request(
            method=method,
            url=url,
            headers=self.headers,
            json=data
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
    """
    List available tools for Ashby operations.
    """
    return [
        # Candidate Management Tools
        types.Tool(
            name="create_candidate",
            description="Creates a new candidate in Ashby",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Candidate's full name"},
                    "email": {"type": "string", "description": "Candidate's email address"},
                    "phone_number": {"type": "string", "description": "Candidate's phone number"}
                },
                "required": ["name", "email"]
            }
        ),
        types.Tool(
            name="search_candidates",
            description="Search for candidates by email and/or name",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Candidate's email"},
                    "name": {"type": "string", "description": "Candidate's name"}
                }
            }
        ),
        types.Tool(
            name="list_candidates",
            description="List candidates with pagination and filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "Page number", "default": 1},
                    "page_size": {"type": "integer", "description": "Results per page", "default": 100},
                    "filters": {
                        "type": "object",
                        "description": "Additional filters to apply"
                    }
                }
            }
        ),
        types.Tool(
            name="get_candidate_info",
            description="Get detailed information about a specific candidate including LinkedIn, resume, and application IDs",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "The unique ID of the candidate"}
                },
                "required": ["candidate_id"]
            }
        ),
        types.Tool(
            name="get_resume_url",
            description="Get a downloadable URL for a candidate's resume file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_handle": {"type": "string", "description": "The file handle from candidate resumeFileHandle.handle field"}
                },
                "required": ["file_handle"]
            }
        ),
        types.Tool(
            name="list_candidate_notes",
            description="List all notes on a candidate's profile",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "The ID of the candidate"},
                    "cursor": {"type": "string", "description": "Pagination cursor for next page"},
                    "limit": {"type": "integer", "description": "Number of results to return", "default": 100}
                },
                "required": ["candidate_id"]
            }
        ),
        types.Tool(
            name="create_candidate_note",
            description="Create a new note on a candidate's profile",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "The ID of the candidate"},
                    "note": {"type": "string", "description": "The note content"},
                    "note_type": {
                        "type": "string",
                        "enum": ["text/plain", "text/html"],
                        "description": "The format of the note (default: text/plain)",
                        "default": "text/plain"
                    }
                },
                "required": ["candidate_id", "note"]
            }
        ),
        types.Tool(
            name="get_application_history",
            description="Get the activity timeline and stage changes for an application",
            inputSchema={
                "type": "object",
                "properties": {
                    "application_id": {"type": "string", "description": "The ID of the application"},
                    "cursor": {"type": "string", "description": "Pagination cursor for next page"},
                    "limit": {"type": "integer", "description": "Number of results to return", "default": 25}
                },
                "required": ["application_id"]
            }
        ),
        types.Tool(
            name="get_application_feedback",
            description="Get interview feedback and scorecards for an application",
            inputSchema={
                "type": "object",
                "properties": {
                    "application_id": {"type": "string", "description": "The ID of the application"},
                    "cursor": {"type": "string", "description": "Pagination cursor for next page"},
                    "limit": {"type": "integer", "description": "Number of results to return", "default": 100}
                },
                "required": ["application_id"]
            }
        ),

        # Job Management Tools
        types.Tool(
            name="create_job",
            description="Creates a new job posting",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Job title"},
                    "description": {"type": "string", "description": "Job description"},
                    "department": {"type": "string", "description": "Department name"},
                    "location": {"type": "string", "description": "Job location"}
                },
                "required": ["title", "description"]
            }
        ),
        types.Tool(
            name="search_jobs",
            description="Search for jobs by title and filters",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Job title to search for"},
                    "location": {"type": "string", "description": "Filter by location"},
                    "department": {"type": "string", "description": "Filter by department"},
                    "include_unlisted": {"type": "boolean", "description": "Include unlisted jobs"}
                }
            }
        ),
        
        # Application Management Tools
        types.Tool(
            name="create_application",
            description="Creates a new application",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "Candidate ID"},
                    "job_id": {"type": "string", "description": "Job ID"},
                    "source": {"type": "string", "description": "Application source"}
                },
                "required": ["candidate_id", "job_id"]
            }
        ),
        types.Tool(
            name="list_applications",
            description="List applications with pagination and filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "Page number", "default": 1},
                    "page_size": {"type": "integer", "description": "Results per page", "default": 100},
                    "filters": {
                        "type": "object",
                        "description": "Additional filters to apply"
                    }
                }
            }
        ),
        
        # Interview Management Tools
        types.Tool(
            name="create_interview",
            description="Creates a new interview",
            inputSchema={
                "type": "object",
                "properties": {
                    "application_id": {"type": "string", "description": "Application ID"},
                    "interviewer_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of interviewer IDs"
                    },
                    "start_time": {"type": "string", "description": "Interview start time (ISO format)"},
                    "duration": {"type": "integer", "description": "Interview duration in minutes"},
                    "type": {"type": "string", "description": "Interview type"}
                },
                "required": ["application_id", "interviewer_ids", "start_time", "duration"]
            }
        ),
        types.Tool(
            name="list_interviews",
            description="List interviews with filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "application_id": {"type": "string", "description": "Filter by application ID"},
                    "start_date": {"type": "string", "description": "Filter by start date"},
                    "end_date": {"type": "string", "description": "Filter by end date"}
                }
            }
        ),
        
        # Analytics Tools
        types.Tool(
            name="get_pipeline_metrics",
            description="Get pipeline metrics for jobs",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Filter by job ID"},
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "Start date"},
                            "end": {"type": "string", "description": "End date"}
                        }
                    }
                }
            }
        ),
        
        # Batch Operations
        types.Tool(
            name="bulk_create_candidates",
            description="Create multiple candidates in a single operation",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "email": {"type": "string"},
                                "phone_number": {"type": "string"}
                            },
                            "required": ["name", "email"]
                        }
                    }
                },
                "required": ["candidates"]
            }
        ),
        types.Tool(
            name="bulk_update_applications",
            description="Update multiple applications in a single operation",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "application_id": {"type": "string"},
                                "updates": {"type": "object"}
                            },
                            "required": ["application_id", "updates"]
                        }
                    }
                },
                "required": ["updates"]
            }
        ),
        types.Tool(
            name="bulk_schedule_interviews",
            description="Schedule multiple interviews in a single operation",
            inputSchema={
                "type": "object",
                "properties": {
                    "interviews": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "application_id": {"type": "string"},
                                "interviewer_ids": {"type": "array", "items": {"type": "string"}},
                                "start_time": {"type": "string"},
                                "duration": {"type": "integer"},
                                "type": {"type": "string"}
                            },
                            "required": ["application_id", "interviewer_ids", "start_time", "duration"]
                        }
                    }
                },
                "required": ["interviews"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls by routing to appropriate Ashby API endpoints."""
    try:
        if name == "create_candidate":
            response = ashby_client._make_request(
                "/candidate.create",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Created candidate: {json.dumps(response, indent=2)}")]
            
        elif name == "search_candidates":
            response = ashby_client._make_request(
                "/candidate.search",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Search results: {json.dumps(response, indent=2)}")]
            
        elif name == "list_candidates":
            response = ashby_client._make_request(
                "/candidate.list",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Candidate list: {json.dumps(response, indent=2)}")]

        elif name == "get_candidate_info":
            response = ashby_client._make_request(
                "/candidate.info",
                method="POST",
                data={"id": arguments["candidate_id"]}
            )
            return [types.TextContent(type="text", text=f"Candidate info: {json.dumps(response, indent=2)}")]

        elif name == "get_resume_url":
            response = ashby_client._make_request(
                "/file.info",
                method="POST",
                data={"fileHandle": arguments["file_handle"]}
            )
            return [types.TextContent(type="text", text=f"Resume file info: {json.dumps(response, indent=2)}")]

        elif name == "list_candidate_notes":
            data = {"candidateId": arguments["candidate_id"]}
            if "cursor" in arguments:
                data["cursor"] = arguments["cursor"]
            if "limit" in arguments:
                data["limit"] = arguments["limit"]
            response = ashby_client._make_request(
                "/candidate.listNotes",
                method="POST",
                data=data
            )
            return [types.TextContent(type="text", text=f"Candidate notes: {json.dumps(response, indent=2)}")]

        elif name == "create_candidate_note":
            note_type = arguments.get("note_type", "text/plain")
            note_content = arguments["note"]
            if note_type == "text/html":
                note_data = {"value": note_content, "type": "text/html"}
            else:
                note_data = note_content

            response = ashby_client._make_request(
                "/candidate.createNote",
                method="POST",
                data={
                    "candidateId": arguments["candidate_id"],
                    "note": note_data
                }
            )
            return [types.TextContent(type="text", text=f"Created note: {json.dumps(response, indent=2)}")]

        elif name == "get_application_history":
            data = {"applicationId": arguments["application_id"]}
            if "cursor" in arguments:
                data["cursor"] = arguments["cursor"]
            if "limit" in arguments:
                data["limit"] = arguments["limit"]
            response = ashby_client._make_request(
                "/application.listHistory",
                method="POST",
                data=data
            )
            return [types.TextContent(type="text", text=f"Application history: {json.dumps(response, indent=2)}")]

        elif name == "get_application_feedback":
            data = {"applicationId": arguments["application_id"]}
            if "cursor" in arguments:
                data["cursor"] = arguments["cursor"]
            if "limit" in arguments:
                data["limit"] = arguments["limit"]
            response = ashby_client._make_request(
                "/applicationFeedback.list",
                method="POST",
                data=data
            )
            return [types.TextContent(type="text", text=f"Application feedback: {json.dumps(response, indent=2)}")]

        elif name == "create_job":
            response = ashby_client._make_request(
                "/job.create",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Created job: {json.dumps(response, indent=2)}")]
            
        elif name == "search_jobs":
            response = ashby_client._make_request(
                "/job.search",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Job search results: {json.dumps(response, indent=2)}")]
            
        elif name == "create_application":
            response = ashby_client._make_request(
                "/application.create",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Created application: {json.dumps(response, indent=2)}")]
            
        elif name == "list_applications":
            response = ashby_client._make_request(
                "/application.list",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Application list: {json.dumps(response, indent=2)}")]
            
        elif name == "create_interview":
            response = ashby_client._make_request(
                "/interview.create",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Created interview: {json.dumps(response, indent=2)}")]
            
        elif name == "list_interviews":
            response = ashby_client._make_request(
                "/interview.list",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Interview list: {json.dumps(response, indent=2)}")]
            
        elif name == "get_pipeline_metrics":
            response = ashby_client._make_request(
                "/analytics.pipeline",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Pipeline metrics: {json.dumps(response, indent=2)}")]
            
        elif name == "bulk_create_candidates":
            response = ashby_client._make_request(
                "/candidate.bulkCreate",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Bulk create results: {json.dumps(response, indent=2)}")]
            
        elif name == "bulk_update_applications":
            response = ashby_client._make_request(
                "/application.bulkUpdate",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Bulk update results: {json.dumps(response, indent=2)}")]
            
        elif name == "bulk_schedule_interviews":
            response = ashby_client._make_request(
                "/interview.bulkSchedule",
                method="POST",
                data=arguments
            )
            return [types.TextContent(type="text", text=f"Bulk schedule results: {json.dumps(response, indent=2)}")]
            
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