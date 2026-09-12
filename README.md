# MCP Ashby Connector

A Model Context Protocol (MCP) server implementation for Ashby integration, allowing LLMs to interact with Ashby's Applicant Tracking System (ATS) data and operations.

## Features

Read-only access to Ashby ATS data:

- **Candidates** — search, list, profiles, resumes, notes
- **Applications** — list, detail, history, feedback/scorecards
- **Jobs & Openings** — search, list, detail, headcount tracking
- **Interviews** — plans, stages, schedules, events
- **Offers & Org** — offers, departments, custom field definitions

No create, update, delete or schedule endpoints are exposed.

## Available Tools

All tools are **read-only**. Every endpoint is verified against the vendored
`openapi.json` by the contract test suite — see [Testing](#testing).

### Candidate
- `search_candidates` — search by name or email
- `list_candidates` — list with pagination
- `get_candidate_info` — profile, LinkedIn, resume handle, `applicationIds`
- `get_resume_url` — downloadable resume URL (may expire)
- `list_candidate_notes` — notes on a profile

### Application
- `list_applications` — list/filter by job, status, date
- `get_application_info` — detail incl. `currentInterviewStage`
- `get_application_history` — activity timeline and stage changes
- `get_application_feedback` — interview feedback and scorecards

### Job & Opening
- `search_jobs` — search by title (`title` is required)
- `list_jobs` — list/filter by status
- `get_job_info` — detail, `expand: ["location", "openings"]`
- `list_openings` — headcount slots with `openingState`
- `get_opening_info` — one opening by UUID
- `search_openings` — **resolve an opening by human-readable identifier** (e.g. `O-342524`)

### Interview
- `list_interviews`, `get_interview_info`
- `list_interview_schedules` — filter by `applicationId` or `interviewStageId`
- `list_interview_events` — exact times, interviewers, locations
- `list_interview_stages` — stages within a plan, in order
- `list_interview_plans`

### Offers & Organization
- `list_offers`, `get_offer_info`
- `list_departments`
- `list_custom_fields` — **all custom field definitions** (`objectType`, `fieldType`, `isPrivate`)

## Cross-referencing HiBob Workforce Planning

HiBob WFP Opening IDs (`O-342524`) and Position IDs (`P-53902`) are stored on the
Ashby side as **opening custom fields**, which are returned inside
`latestVersion.customFields` on every opening.

To go from a HiBob ID to the Ashby opening and its job:

```
1. list_custom_fields()                    # which Opening field holds the HiBob ID?
2. search_openings(identifier="O-342524")  # if held in the opening's identifier
   -- or --
   list_openings()                         # then match on the custom field value
3. get_job_info(id=<latestVersion.jobIds[0]>, expand=["openings"])
```

`list_openings` returns `openingState` (`Approved`/`Open`/`Closed`/`Draft`/`Filled`)
alongside `latestVersion.jobIds`, which answers "what is the status of this opening
and which Ashby job does it correspond to?" in a single call.

> **Note:** custom fields flagged `isPrivate` are only readable by an API key granted
> the "Allow access to non-offer private fields" permission. Request this when issuing
> the key, or the HiBob identifiers may come back missing rather than wrong.

## Testing

```bash
uv run --with pytest --with mcp --with requests --with python-dotenv python -m pytest tests/ -q
```

- **`tests/test_tool_contract.py`** — offline. Validates every tool against the vendored
  official Ashby spec: the endpoint exists, no parameter is hallucinated, every required
  parameter is declared, nothing mutating is exposed, and each tool routes where it claims.
  Runs with no network and no API key.
- **`tests/test_live_api.py`** — hits the real API. Auto-skips when `ASHBY_API_KEY` is
  missing or rejected, so the command above is always safe. Validates the HiBob
  cross-reference end to end once a working key is in `.env`.
- **`tests/stub_ashby.py`** — a spec-shaped fake Ashby used to exercise the live suite
  without a real key:

  ```bash
  python tests/stub_ashby.py 8731 &
  ASHBY_API_BASE=http://127.0.0.1:8731 python -m pytest tests/test_live_api.py -q
  ```

  Set `HIBOB=0` on the stub to confirm the HiBob assertions genuinely fail when the
  identifiers are absent.

## API Limitations

The following features are visible in the Ashby UI but **not available via the API**:
- Email communication history
- SMS/text message history

## Example Workflows

### Get candidate's LinkedIn and resume
```
1. search_candidates(name="John Doe")
2. get_candidate_info(candidate_id="...")
3. get_resume_url(file_handle="...")
```

### Review notes
```
1. get_candidate_info(candidate_id="...")
2. list_candidate_notes(candidate_id="...")
```

### Track application progress
```
1. get_candidate_info(candidate_id="...")
2. get_application_history(application_id="...")
3. get_application_feedback(application_id="...")
```

## Configuration
### Model Context Protocol

To use this server with the Model Context Protocol, you need to configure it in your `claude_desktop_config.json` file. Add the following entry to the `mcpServers` section:

```json
{
    "mcpServers": {
        "ashby": {
            "command": "uvx",
            "args": [
                "--from",
                "mcp-ashby-connector",
                "ashby"
            ],
            "env": {
                "ASHBY_API_KEY": "YOUR_ASHBY_API_KEY"
            }
        }
    }
}
```

Replace `YOUR_ASHBY_API_KEY` with your Ashby API key.

## Project Structure

```
src/
  ashby/
    server.py      # MCP server implementation (read-only)
tests/
  test_tool_contract.py  # Offline: tools vs. vendored openapi.json
  test_live_api.py       # Live: real API, auto-skips without a valid key
  stub_ashby.py          # Spec-shaped fake Ashby for exercising the live suite
openapi.json       # Vendored official Ashby OpenAPI spec
```

## Dependencies

The project requires the following Python packages:
- mcp
- requests
- python-dotenv
