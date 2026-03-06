# MCP Ashby Connector

A Model Context Protocol (MCP) server implementation for Ashby integration, allowing LLMs to interact with Ashby's Applicant Tracking System (ATS) data and operations.

## Features

- **Candidate Management**: Create, search, list, and get detailed candidate information
- **Candidate Profiles**: Access LinkedIn profiles, resumes, notes, and activity history
- **Job Management**: Create, search, and list job postings
- **Application Management**: Create, list, update, and track application history
- **Interview Management**: Create, list, schedule interviews, and access feedback/scorecards
- **Analytics & Reporting**: Pipeline metrics and performance tracking
- **Batch Operations**: Bulk create, update, and schedule operations

## Available Tools

### Candidate Tools
- `create_candidate` - Create a new candidate
- `search_candidates` - Search for candidates by name or email
- `list_candidates` - List candidates with pagination
- **`get_candidate_info`** - Get detailed candidate info including LinkedIn, resume, and application IDs
- **`get_resume_url`** - Get a downloadable URL for a candidate's resume
- **`list_candidate_notes`** - List all notes on a candidate's profile
- **`create_candidate_note`** - Add a new note to a candidate

### Application Tools
- `create_application` - Create a new application
- `list_applications` - List applications with filtering
- **`get_application_history`** - Get activity timeline and stage changes for an application
- **`get_application_feedback`** - Get interview feedback and scorecards

### Job Tools
- `create_job` - Create a new job posting
- `search_jobs` - Search for jobs

### Interview Tools
- `create_interview` - Schedule a new interview
- `list_interviews` - List scheduled interviews

### Analytics Tools
- `get_pipeline_metrics` - Get recruitment pipeline metrics

### Batch Operations
- `bulk_create_candidates` - Create multiple candidates at once
- `bulk_update_applications` - Update multiple applications at once
- `bulk_schedule_interviews` - Schedule multiple interviews at once

**Note**: Tools marked in **bold** are newly added for enhanced candidate profile access.

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

### Review and add notes
```
1. get_candidate_info(candidate_id="...")
2. list_candidate_notes(candidate_id="...")
3. create_candidate_note(candidate_id="...", note="Great technical skills")
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
    server.py      # Main MCP server implementation
```

## Dependencies

The project requires the following Python packages:
- mcp
- requests
- python-dotenv
