"""Pure data: the Macro-style tool catalog (no runtime deps)."""
from __future__ import annotations

# This list is also maintained in mcp_server.py for the live server.
# Keep in sync.

TOOLS_CATALOG = [
    {"name": "SelfKnowledge", "description": "Learn what this workspace/MCP server is.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "server/discover", "description": "MCP 2026-07-28 discovery.", "inputSchema": {"type": "object", "properties": {}}},
    # ... (the full list is defined in mcp_server.py to avoid duplication during active dev)
]

def get_catalog():
    # In real: return the big list. For now, load from sibling or hardcode key ones.
    # To keep single source, we exec the server module in a protected way in the server file.
    return TOOLS_CATALOG
