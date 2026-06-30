## Citation Extraction MCP Server

This project exposes citation extraction as a FastMCP server.

### Tools

- `extract`: extracts bibliographic metadata from an academic reference.
- `verify`: extracts metadata and verifies it against external sources.

### Run

Set an API key before starting the server:

```bash
export OPENROUTER_API_KEY="..."
```

```bash
uv run python -m fastApi.main
```

or after installing the project:

```bash
citation-extraction-mcp
```
