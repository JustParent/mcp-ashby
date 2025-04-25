# MCP Ashby Connector

A Model Context Protocol (MCP) server implementation for Ashby integration, allowing LLMs to interact with Ashby's Applicant Tracking System (ATS) data and operations.

## Features

- Candidate Management (create, search, list)
- Job Management (create, search, list)
- Application Management (create, list, update)
- Interview Management (create, list, schedule)
- Analytics & Reporting (pipeline metrics)
- Batch Operations (bulk create/update/schedule)

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
