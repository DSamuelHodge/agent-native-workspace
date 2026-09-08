"""Agent-native workspace: data model + stateless MCP server (~67+ Macro tools)."""

try:
    from agent_native_workspace.db import get_engine, get_sessionmaker
    from agent_native_workspace.models import Base
except Exception:  # noqa: BLE001  # optional deps for catalog-only / no-sqlalchemy use cases
    get_engine = None  # type: ignore
    get_sessionmaker = None  # type: ignore
    Base = None  # type: ignore

__all__ = ["Base", "get_engine", "get_sessionmaker", "mcp_server"]

# Lazy submodules
try:
    from . import mcp_server
except Exception:  # noqa: BLE001
    mcp_server = None  # type: ignore

try:
    from . import tools_catalog
except Exception:  # noqa: BLE001
    tools_catalog = None  # type: ignore
