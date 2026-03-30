# toolbox-mcp

Minimal MCP for toolbox operations.

## Tools
- `list_tools()`
- `check_tool(name)`
- `run_tool(name)`
- `record_result(name, payload)`

## Run

```bash
python3 /Users/ryan/meta-agent/tools/toolbox-mcp/server.py
```

Guarded whitelist commands are defined in `server.py` (`TOOL_REGISTRY`).
