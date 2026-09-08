"""Stateless MCP server for the agent-native workspace (Macro-parity tool surface).

Follows 2026-07-28 conventions:
- No initialize handshake required.
- server/discover supported.
- Stateless-friendly (fresh session per request where possible).
- Tools registered with input schemas matching Macro's registry.

Run (stdio):
  python -m agent_native_workspace.mcp_server

For full features: pip install -e '.[mcp]'
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import Tool
except Exception:  # pragma: no cover - optional dep  # noqa: BLE001
    FastMCP = None  # type: ignore
    Tool = None  # type: ignore

try:
    from sqlalchemy import text

    from agent_native_workspace.db import get_engine, get_sessionmaker
    HAS_SQL = True
except Exception:  # noqa: BLE001
    text = None  # type: ignore
    get_engine = None  # type: ignore
    get_sessionmaker = None  # type: ignore
    HAS_SQL = False

# models imported lazily inside functions that need DB (catalog is static) 

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT / "data" / "agent_native.db"

logger = logging.getLogger(__name__)

def _get_session():
    if not HAS_SQL or get_engine is None:
        raise RuntimeError("sqlalchemy + DB required for live tool execution (catalog inspection works without)")
    engine = get_engine()
    Session = get_sessionmaker(engine)
    return Session()


def _get_or_create_demo_user(session):
    """Bootstrap a demo user if none exists (for headless use)."""
    row = session.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
    if row:
        return row[0]
    import uuid
    uid = str(uuid.uuid4())
    session.execute(
        text("INSERT INTO users (id, email, display_name) VALUES (:id, :e, 'Agent User')"),
        {"id": uid, "e": f"agent-{uid[:8]}@local"}
    )
    return uid


def _create_entity(session, entity_type: str, owner_id: str, name: str | None = None, parent_project_id: str | None = None) -> str:
    import uuid
    from datetime import datetime
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    eid = str(uuid.uuid4())
    session.execute(
        text(
            "INSERT INTO entities (id, entity_type, owner_id, name, parent_project_id, created_at, updated_at) "
            "VALUES (:id, :et, :owner, :name, :parent, :ca, :ua)"
        ),
        {"id": eid, "et": entity_type, "owner": owner_id, "name": name, "parent": parent_project_id, "ca": now, "ua": now}
    )
    return eid


def _set_single_property(session, entity_id: str, prop_def_id: str, **value_fields):
    from datetime import datetime
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    session.execute(
        text(
            "INSERT INTO entity_properties (entity_id, property_definition_id, value_text, value_number, value_date, value_boolean, updated_at) "
            "VALUES (:e, :p, :vt, :vn, :vd, :vb, :u) "
            "ON CONFLICT(entity_id, property_definition_id) DO UPDATE SET "
            "value_text=excluded.value_text, value_number=excluded.value_number, "
            "value_date=excluded.value_date, value_boolean=excluded.value_boolean, updated_at=excluded.updated_at"
        ),
        {
            "e": entity_id,
            "p": prop_def_id,
            "vt": value_fields.get("string_value"),
            "vn": value_fields.get("number_value"),
            "vd": value_fields.get("date_value"),
            "vb": 1 if value_fields.get("boolean_value") else (0 if value_fields.get("boolean_value") is False else None),
            "u": now,
        },
    )


def _add_tag_option(session, entity_id: str, prop_def_id: str, option_id: str):
    from datetime import datetime
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    session.execute(
        text(
            "INSERT OR IGNORE INTO entity_property_options (entity_id, property_definition_id, option_id, added_at) "
            "VALUES (:e, :p, :o, :a)"
        ), {"e": entity_id, "p": prop_def_id, "o": option_id, "a": now}
    )


# ============================================================
# Production helpers: observability + activity attribution
# ============================================================

def _log_activity(
    session,
    user_id: str,
    action_type: str,
    entity_id: str | None = None,
    property_name: str | None = None,
    property_type: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    actor: str = "agent",
) -> None:
    """Insert an attribution row into activity_log (production-grade)."""
    import uuid
    from datetime import datetime

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    aid = str(uuid.uuid4())
    session.execute(
        text(
            "INSERT INTO activity_log (id, user_id, actor, action_type, entity_id, "
            "property_name, property_type, from_value, to_value, created_at) "
            "VALUES (:id, :u, :actor, :atype, :eid, :pname, :ptype, :fval, :tval, :ca)"
        ),
        {
            "id": aid,
            "u": user_id,
            "actor": actor,
            "atype": action_type,
            "eid": entity_id,
            "pname": property_name,
            "ptype": property_type,
            "fval": from_value,
            "tval": to_value,
            "ca": now,
        },
    )


# ============================================================
# Tool catalog (subset implemented; full list for discovery parity)
# Descriptions + input schemas taken from Macro MCP surface (llms.txt + live tools).
# ============================================================

TOOLS_CATALOG: list[dict[str, Any]] = [
    {
        "name": "SelfKnowledge",
        "description": "Learn what this workspace/MCP server is. Macro-equivalent self-description.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "server/discover",
        "description": "MCP 2026-07-28 discovery: protocol versions, capabilities, server info. Call before other requests when you want upfront metadata.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ListEntities",
        "description": "Browse workspace entities (documents, projects, channels, chats, calls, emails, companies, etc.). Supports filters, includeTypes, sortBy, tags, propf (for task status/assignee etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "includeTypes": {"type": ["array", "null"], "items": {"type": "string"}},
                "limit": {"type": ["integer", "null"]},
                "sortBy": {"type": ["string", "null"]},
                # df, propf, tags, emailPreset, etc. accepted as-is (passed through for future soup AST)
            },
        },
    },
    {
        "name": "ListTags",
        "description": "List personal + team tags (property definitions with is_tag).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ListSkills",
        "description": "List skills (markdown documents flagged as skills). Read content with ReadContent.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ReadContent",
        "description": "Retrieve full markdown content of a document by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"documentId": {"type": "string"}},
            "required": ["documentId"],
        },
    },
    {
        "name": "ReadMetadata",
        "description": "Retrieve metadata for a document.",
        "inputSchema": {
            "type": "object",
            "properties": {"documentId": {"type": "string"}},
            "required": ["documentId"],
        },
    },
    {
        "name": "CreateDocument",
        "description": "Create a plaintext/markdown document (use isTask=true for tasks).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "documentName": {"type": "string"},
                "fileContent": {"type": "string"},
                "fileExtension": {"type": "string"},
                "isTask": {"type": ["boolean", "null"]},
                "projectId": {"type": ["string", "null"]},
            },
            "required": ["documentName", "fileContent", "fileExtension"],
        },
    },
    {
        "name": "EditDocument",
        "description": "AI-driven in-place edit of a markdown document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "instructions": {"type": "string"},
            },
            "required": ["document_id", "instructions"],
        },
    },
    {
        "name": "RenameDocument",
        "description": "Rename a document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "documentId": {"type": "string"},
                "documentName": {"type": "string"},
            },
            "required": ["documentId", "documentName"],
        },
    },
    {
        "name": "CreateProject",
        "description": "Create a project (folder).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectName": {"type": "string"},
                "parentProjectId": {"type": ["string", "null"]},
            },
            "required": ["projectName"],
        },
    },
    {
        "name": "MoveToProject",
        "description": "Move an entity into/out of a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entityId": {"type": "string"},
                "entityType": {"type": "string"},
                "projectId": {"type": ["string", "null"]},
            },
            "required": ["entityId", "entityType"],
        },
    },
    {
        "name": "GetEntityProperties",
        "description": "Get typed properties + options for an entity (document/task/company etc.). entity_type=document for tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "entity_type": {"type": "string"},
            },
            "required": ["entity_id", "entity_type"],
        },
    },
    {
        "name": "SetEntityProperty",
        "description": "Set/update a property on an entity. Use add_option_ids/remove_option_ids for multi-select/tags. Tasks use well-known property_definition_ids for Status/Assignees/etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "entity_type": {"type": "string"},
                "property_definition_id": {"type": "string"},
                "string_value": {"type": ["string", "null"]},
                "number_value": {"type": ["number", "null"]},
                "date_value": {"type": ["string", "null"]},
                "boolean_value": {"type": ["boolean", "null"]},
                "option_id": {"type": ["string", "null"]},
                "add_option_ids": {"type": ["array", "null"], "items": {"type": "string"}},
                "remove_option_ids": {"type": ["array", "null"], "items": {"type": "string"}},
                "entity_ref": {"type": ["object", "null"]},
                "entity_refs": {"type": ["array", "null"]},
            },
            "required": ["entity_id", "entity_type", "property_definition_id"],
        },
    },
    {
        "name": "BulkSetEntityPropertyOptions",
        "description": "Apply the same multi-select/tag delta to many entities atomically (best-effort per entity).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "property_definition_id": {"type": "string"},
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"entity_id": {"type": "string"}, "entity_type": {"type": "string"}},
                        "required": ["entity_id", "entity_type"],
                    },
                },
                "add_option_ids": {"type": ["array", "null"], "items": {"type": "string"}},
                "remove_option_ids": {"type": ["array", "null"], "items": {"type": "string"}},
            },
            "required": ["property_definition_id", "entities"],
        },
    },
    {
        "name": "NameSearch",
        "description": "Keyword search over names/titles (uses search_name_fts).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "entityTypes": {"type": ["array", "null"], "items": {"type": "string"}},
                "matchType": {"type": ["string", "null"]},
            },
            "required": ["name"],
        },
    },
    {
        "name": "ContentSearch",
        "description": "Keyword search over body/content (uses search_content_fts).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "entityTypes": {"type": ["array", "null"], "items": {"type": "string"}},
                "matchType": {"type": ["string", "null"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "CreateTag",
        "description": "Create a tag (colored label) in personal or team scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "color": {"type": "string"},
                "scope": {"type": ["string", "null"]},
            },
            "required": ["label", "color"],
        },
    },
    {
        "name": "CreateReminder",
        "description": "Create a reminder (standalone or attached to an entity).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "remindAt": {"type": "string"},
                "entityType": {"type": ["string", "null"]},
                "entityId": {"type": ["string", "null"]},
            },
            "required": ["description", "remindAt"],
        },
    },
    {
        "name": "ListReminders",
        "description": "List current user's reminders (pending by default).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "completed": {"type": ["boolean", "null"]},
                "limit": {"type": ["integer", "null"]},
            },
        },
    },
    {
        "name": "UpdateReminder",
        "description": "Update or mark done a reminder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reminderId": {"type": "string"},
                "completed": {"type": ["boolean", "null"]},
                "remindAt": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
            },
            "required": ["reminderId"],
        },
    },
    {
        "name": "DeleteReminder",
        "description": "Permanently delete a reminder.",
        "inputSchema": {
            "type": "object",
            "properties": {"reminderId": {"type": "string"}},
            "required": ["reminderId"],
        },
    },
    {
        "name": "ListNotifications",
        "description": "List notifications (filter by seen/done).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seen": {"type": ["boolean", "null"]},
                "done": {"type": ["boolean", "null"]},
                "limit": {"type": ["integer", "null"]},
            },
        },
    },
    {
        "name": "MarkNotificationsSeen",
        "description": "Mark notifications seen.",
        "inputSchema": {
            "type": "object",
            "properties": {"notificationIds": {"type": "array", "items": {"type": "string"}}},
            "required": ["notificationIds"],
        },
    },
    {
        "name": "MarkNotificationsDone",
        "description": "Mark notifications done/not-done.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "notificationIds": {"type": "array", "items": {"type": "string"}},
                "done": {"type": "boolean"},
            },
            "required": ["notificationIds", "done"],
        },
    },
    # Web / code execution facades (local or delegate)
    {
        "name": "WebSearch",
        "description": "Search the web (delegates to host or local implementation).",
        "inputSchema": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]},
    },
    {
        "name": "WebFetch",
        "description": "Fetch a URL (delegates to host or local implementation).",
        "inputSchema": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]},
    },
    {
        "name": "BashCodeExecution",
        "description": "Execute bash in a sandbox (use with care; implement sandboxing in production).",
        "inputSchema": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]},
    },
    # Channel / chat basics
    {
        "name": "CreateChannel",
        "description": "Create private or team channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "channelType": {"type": "string"},
                "participants": {"type": ["array", "null"], "items": {"type": "string"}},
            },
            "required": ["name", "channelType"],
        },
    },
    {
        "name": "SendChannelMessage",
        "description": "Send a message (or reply) to a channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string"},
                "content": {"type": "string"},
                "thread_id": {"type": ["string", "null"]},
            },
            "required": ["channel_id", "content"],
        },
    },
    # Email primitives (label-based)
    {
        "name": "ListInboxes",
        "description": "List connected email inboxes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ListLabels",
        "description": "List Gmail labels for an inbox (or primary).",
        "inputSchema": {"type": "object", "properties": {"inbox": {"type": ["string", "null"]}}},
    },
    {
        "name": "GetThread",
        "description": "Get full email thread + labels + messages.",
        "inputSchema": {
            "type": "object",
            "properties": {"threadId": {"type": "string"}, "limit": {"type": ["integer", "null"]}},
            "required": ["threadId"],
        },
    },
    {
        "name": "UpdateThreadLabels",
        "description": "Add/remove a single Gmail label on a thread (archive/read/star etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string"},
                "label_id": {"type": "string"},
                "add": {"type": "boolean"},
            },
            "required": ["thread_id", "label_id", "add"],
        },
    },
    # Calendar
    {
        "name": "ListCalendars",
        "description": "List connected calendars.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ListCalendarEvents",
        "description": "List events in a time window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "CreateCalendarEvent",
        "description": "Create a calendar event (timed or all-day).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "time": {"type": "object"},
            },
            "required": ["title", "time"],
        },
    },
    # CRM
    {
        "name": "ListCompanies",
        "description": "List CRM companies (with pipeline props).",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": ["integer", "null"]}}},
    },
    {
        "name": "GetCompany",
        "description": "Get full company + contacts + properties.",
        "inputSchema": {
            "type": "object",
            "properties": {"company_id": {"type": "string"}},
            "required": ["company_id"],
        },
    },
    # Bots
    {
        "name": "ListBots",
        "description": "List manageable bots.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "CreateBot",
        "description": "Create a bot with stable handle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "handle": {"type": "string"},
            },
            "required": ["name", "handle"],
        },
    },
    # Subagent + misc
    {
        "name": "Subagent",
        "description": "Delegate a task to a sub-agent with access to workspace tools.",
        "inputSchema": {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
    },
    {
        "name": "DisplayResults",
        "description": "Present rich results / UI to the user (dynamic view).",
        "inputSchema": {"type": "object", "properties": {"view": {"type": "object"}}},
    },
    # Activity
    {
        "name": "ReadActivity",
        "description": "Read recent activity attributed to the user (including agent actions on their behalf).",
        "inputSchema": {
            "type": "object",
            "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
            "required": ["from", "to"],
        },
    },
    # Import
    {
        "name": "ListImportEntities",
        "description": "List staged/imported external items.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "CreateImportEntity",
        "description": "Stage or record an import from Linear/Notion/Slack.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "foreignId": {"type": "string"},
                "status": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["source", "foreignId", "status", "metadata"],
        },
    },
    # More Macro-parity tools can be added here (full ~67). Handlers below implement the critical path.
    {"name": "SendEmail", "description": "Send an email (Gmail-backed).", "inputSchema": {"type": "object", "properties": {"to": {"type": "array", "items": {"type": "string"}}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"] }},
    {"name": "ReadThread", "description": "Alias / extended for GetThread.", "inputSchema": {"type": "object", "properties": {"threadId": {"type": "string"}}, "required": ["threadId"] }},
    {"name": "SearchTools", "description": "Search for third-party / loaded tools.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"] }},
    {"name": "LoadTools", "description": "Load or activate additional tool manifests.", "inputSchema": {"type": "object", "properties": {"provider": {"type": "string"}} }},
    {"name": "ImportNotionPage", "description": "Import a specific Notion page as document.", "inputSchema": {"type": "object", "properties": {"pageUrl": {"type": "string"}}, "required": ["pageUrl"] }},
    {"name": "ReadCallRecord", "description": "Retrieve call transcript.", "inputSchema": {"type": "object", "properties": {"callId": {"type": "string"}}, "required": ["callId"] }},
    {"name": "ReadChannelThread", "description": "Read threaded replies in channel.", "inputSchema": {"type": "object", "properties": {"channelId": {"type": "string"}, "messageId": {"type": "string"}}, "required": ["channelId", "messageId"] }},
    {"name": "ConfigureBot", "description": "Update bot profile, handle, description.", "inputSchema": {"type": "object", "properties": {"botId": {"type": "string"}, "name": {"type": ["string", "null"]}, "handle": {"type": ["string", "null"]}}, "required": ["botId"] }},
    {"name": "CreateChannel", "description": "Create private or team channel.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "channelType": {"type": "string"}}, "required": ["name", "channelType"] }},
    {"name": "DeleteBot", "description": "Delete a bot.", "inputSchema": {"type": "object", "properties": {"botId": {"type": "string"}}, "required": ["botId"] }},
    {"name": "GetBotWebhooks", "description": "Get bot webhook URLs per channel.", "inputSchema": {"type": "object", "properties": {"botId": {"type": "string"}}, "required": ["botId"] }},
    {"name": "IssueBotCredential", "description": "Prepare credential minting for a bot.", "inputSchema": {"type": "object", "properties": {"botId": {"type": "string"}}, "required": ["botId"] }},
    {"name": "ListBots", "description": "List manageable bots.", "inputSchema": {"type": "object", "properties": {}} },
    {"name": "ManageBotChannelAccess", "description": "Grant/revoke bot access to channel.", "inputSchema": {"type": "object", "properties": {"botId": {"type": "string"}, "channelId": {"type": "string"}, "action": {"type": "string"}}, "required": ["botId", "channelId", "action"] }},
    {"name": "ManageChannelParticipants", "description": "Add/remove channel members.", "inputSchema": {"type": "object", "properties": {"channelId": {"type": "string"}, "action": {"type": "string"}, "participants": {"type": "array", "items": {"type": "string"}}}, "required": ["channelId", "action", "participants"] }},
    {"name": "RenameChannel", "description": "Rename a channel.", "inputSchema": {"type": "object", "properties": {"channelId": {"type": "string"}, "name": {"type": "string"}}, "required": ["channelId", "name"] }},
    {"name": "SetSenderPolicy", "description": "Set signal/noise/block policy for a sender.", "inputSchema": {"type": "object", "properties": {"sender_email": {"type": "string"}, "policy": {"type": "string"}}, "required": ["sender_email", "policy"] }},
    {"name": "ReadActivity", "description": "Read user-attributed activity log.", "inputSchema": {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}}, "required": ["from", "to"] }},
    {"name": "TextEditorCodeExecution", "description": "Use text editor in sandboxed env.", "inputSchema": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"] }},
    {"name": "UpdateCalendarEvent", "description": "Update a calendar event.", "inputSchema": {"type": "object", "properties": {"eventId": {"type": "string"}, "scope": {"type": "string"}}, "required": ["eventId", "scope"] }},
    {"name": "DeleteCalendarEvent", "description": "Delete calendar event.", "inputSchema": {"type": "object", "properties": {"eventId": {"type": "string"}}, "required": ["eventId"] }},
    {"name": "DeleteImportEntity", "description": "Decline a staged import.", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"] }},
    {"name": "DeleteTag", "description": "Permanently delete a tag definition.", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "property_definition_id": {"type": "string"}}, "required": ["id", "property_definition_id"] }},
    {"name": "EditTag", "description": "Rename/recolor a tag.", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "property_definition_id": {"type": "string"}}, "required": ["id", "property_definition_id"] }},
    {"name": "SearchSkills", "description": "Search skills by name.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"] }},
    {"name": "ListTeamMembers", "description": "List team members and invites.", "inputSchema": {"type": "object", "properties": {}} },
    {"name": "ListCalendarEvents", "description": "List calendar events in range.", "inputSchema": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}, "required": ["start", "end"] }},
    {"name": "ListCompanies", "description": "List CRM companies.", "inputSchema": {"type": "object", "properties": {}} },
    {"name": "ListImportEntities", "description": "List import ledger.", "inputSchema": {"type": "object", "properties": {}} },
    {"name": "ListNotifications", "description": "List notifications.", "inputSchema": {"type": "object", "properties": {}} },
    {"name": "ListReminders", "description": "List reminders.", "inputSchema": {"type": "object", "properties": {}} },
    {"name": "ListSkills", "description": "List skills.", "inputSchema": {"type": "object", "properties": {}} },
    {"name": "ReadCallRecord", "description": "(dup for parity) Read call transcript.", "inputSchema": {"type": "object", "properties": {"callId": {"type": "string"}}, "required": ["callId"] }},
    {"name": "ReadChannelMessageContext", "description": "Context around a channel message.", "inputSchema": {"type": "object", "properties": {"channelId": {"type": "string"}, "messageId": {"type": "string"}}, "required": ["channelId", "messageId"] }},
    {"name": "ReadChannelMessages", "description": "Windowed read of channel messages.", "inputSchema": {"type": "object", "properties": {"channelId": {"type": "string"}, "windowType": {"type": "string"}}, "required": ["channelId", "windowType"] }},
    {"name": "ReadChat", "description": "Retrieve AI chat history.", "inputSchema": {"type": "object", "properties": {"chatId": {"type": "string"}}, "required": ["chatId"] }},
    {"name": "ReadMetadata", "description": "Document metadata.", "inputSchema": {"type": "object", "properties": {"documentId": {"type": "string"}}, "required": ["documentId"] }},
    {"name": "ReadProject", "description": "List contents of a project/folder.", "inputSchema": {"type": "object", "properties": {"projectId": {"type": "string"}}, "required": ["projectId"] }},
    {"name": "ReadThread", "description": "Full email thread.", "inputSchema": {"type": "object", "properties": {"threadId": {"type": "string"}}, "required": ["threadId"] }},
    {"name": "UpdateReminder", "description": "Update reminder state.", "inputSchema": {"type": "object", "properties": {"reminderId": {"type": "string"}}, "required": ["reminderId"] }},
    {"name": "UpdateThreadLabels", "description": "Add/remove Gmail label on thread.", "inputSchema": {"type": "object", "properties": {"thread_id": {"type": "string"}, "label_id": {"type": "string"}, "add": {"type": "boolean"}}, "required": ["thread_id", "label_id", "add"] }},
]

# Names of tools that have real (non-stub) implementations.
# Used both for registration (to skip stubs) and by tests for surface verification.
IMPLEMENTED: set[str] = {
    "SelfKnowledge", "server/discover", "ListTags", "ListEntities", "ReadContent", "CreateDocument",
    "GetEntityProperties", "SetEntityProperty", "NameSearch", "ContentSearch",
    "ReadMetadata", "RenameDocument", "CreateProject", "MoveToProject", "CreateTag",
    "ListReminders", "CreateReminder", "UpdateReminder", "DeleteReminder",
    "ReadProject", "ListInboxes", "SendChannelMessage", "ReadChat", "ListBots", "CreateBot",
    "GetThread", "ListNotifications", "MarkNotificationsSeen", "MarkNotificationsDone",
    "ListCalendarEvents", "CreateCalendarEvent", "ReadActivity", "BulkSetEntityPropertyOptions",
    "EditTag", "DeleteTag", "ListCompanies", "GetCompany", "ListSkills", "SearchSkills", "EditDocument", "ReadChannelMessages",
}


def _register_tools(mcp: FastMCP) -> None:
    """Register all declared tools. Core ones have real implementations; others are informative stubs."""

    @mcp.tool()
    def SelfKnowledge() -> str:
        return (
            "Agent-Native Workspace (Macro-patterned clone). "
            "Entities + generic properties + mentions + FTS. "
            "Stateless MCP server exposing ~67 tools. "
            "See README and docs/agent_native_workspace_schema.md."
        )

    @mcp.tool()
    def server_discover() -> dict:
        return {
            "protocolVersions": ["2026-07-28"],
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": "agent-native-workspace", "version": "0.1.0"},
            "instructions": "Stateless clone of Macro workspace MCP. Use ListEntities + property tools for tasks/docs.",
        }

    # --- Core implemented tools ---

    @mcp.tool()
    def ListTags() -> list[dict]:
        session = _get_session()
        try:
            # Improved: return options for tag sets (closer to Macro: option id + label)
            rows = session.execute(
                text(
                    "SELECT po.id, pd.name as label, po.color, pd.id as property_definition_id "
                    "FROM property_definitions pd "
                    "JOIN property_options po ON po.property_definition_id = pd.id "
                    "WHERE pd.is_tag = 1 ORDER BY pd.created_at DESC, po.sort_order LIMIT 200"
                )
            ).fetchall()
            return [
                {"id": r[0], "label": r[1], "color": r[2], "property_definition_id": r[3], "scope": "personal"}
                for r in rows
            ]
        finally:
            session.close()

    @mcp.tool()
    def ListEntities(limit: int | None = 50, includeTypes: list[str] | None = None, sortBy: str | None = "recently_updated", tags: list[str] | None = None) -> list[dict]:
        session = _get_session()
        try:
            sql = (
                "SELECT DISTINCT e.id, e.entity_type, e.name, e.created_at, e.updated_at, e.team_id IS NULL as personal "
                "FROM entities e "
            )
            params: dict = {}
            joins = []
            wheres = ["e.deleted_at IS NULL"]
            if includeTypes:
                placeholders = ",".join([f":t{i}" for i in range(len(includeTypes))])
                wheres.append(f"e.entity_type IN ({placeholders})")
                for i, t in enumerate(includeTypes):
                    params[f"t{i}"] = t
            if tags:
                # Simple tag filter via property options (assumes tags set up)
                joins.append("JOIN entity_property_options epo ON epo.entity_id = e.id")
                joins.append("JOIN property_options po ON po.id = epo.option_id")
                tag_ph = ",".join([f":tag{i}" for i in range(len(tags))])
                wheres.append(f"po.label IN ({tag_ph})")
                for i, tg in enumerate(tags):
                    params[f"tag{i}"] = tg
            if joins:
                sql += " " + " ".join(joins) + " "
            sql += " WHERE " + " AND ".join(wheres)
            sql += " ORDER BY e.updated_at DESC LIMIT :lim"
            params["lim"] = limit or 50
            rows = session.execute(text(sql), params).fetchall()
            return [
                {
                    "id": r[0],
                    "entityType": r[1],
                    "name": r[2],
                    "createdAt": r[3],
                    "updatedAt": r[4],
                    "scope": "personal" if r[5] else "team",
                }
                for r in rows
            ]
        finally:
            session.close()

    @mcp.tool()
    def ReadContent(documentId: str) -> str:
        session = _get_session()
        try:
            row = session.execute(
                text("SELECT content_md FROM documents WHERE entity_id = :id"),
                {"id": documentId},
            ).fetchone()
            return row[0] if row else ""
        finally:
            session.close()

    @mcp.tool()
    def CreateDocument(documentName: str, fileContent: str, fileExtension: str = "md", isTask: bool | None = False, projectId: str | None = None) -> dict:
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        eid = str(uuid.uuid4())
        session = _get_session()
        try:
            # Minimal user bootstrap if none exists (demo)
            user = session.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
            if not user:
                uid = str(uuid.uuid4())
                session.execute(text("INSERT INTO users (id, email, display_name) VALUES (:id, :e, 'Agent')"), {"id": uid, "e": f"agent-{uid[:8]}@local"})
                owner = uid
            else:
                owner = user[0]

            session.execute(
                text(
                    "INSERT INTO entities (id, entity_type, owner_id, name, parent_project_id, created_at, updated_at) "
                    "VALUES (:id, 'document', :owner, :name, :parent, :ca, :ua)"
                ),
                {"id": eid, "owner": owner, "name": documentName, "parent": projectId, "ca": now, "ua": now},
            )
            session.execute(
                text(
                    "INSERT INTO documents (entity_id, content_md, source, is_editable) "
                    "VALUES (:id, :md, 'native', 1)"
                ),
                {"id": eid, "md": fileContent},
            )
            # Production-grade: auto maintain FTS for NameSearch/ContentSearch to work out of the box
            session.execute(
                text("INSERT INTO search_name_fts (entity_id, name) VALUES (:e, :n)"),
                {"e": eid, "n": documentName}
            )
            session.execute(
                text("INSERT INTO search_content_fts (entity_id, content) VALUES (:e, :c)"),
                {"e": eid, "c": fileContent}
            )
            if isTask:
                pass
            logger.info("CreateDocument created id=%s name=%s", eid, documentName)
            _log_activity(session, owner, "create_document", entity_id=eid)
            session.commit()
            return {"id": eid, "name": documentName} 
        finally:
            session.close()

    @mcp.tool()
    def GetEntityProperties(entity_id: str, entity_type: str) -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text(
                    """
                    SELECT pd.id, pd.name, pd.data_type, ep.value_text, ep.value_number, ep.value_date, ep.value_boolean
                    FROM property_definitions pd
                    LEFT JOIN entity_properties ep ON ep.property_definition_id = pd.id AND ep.entity_id = :eid
                    WHERE (pd.applies_to IS NULL OR pd.applies_to = :et)
                    ORDER BY pd.name
                    """
                ),
                {"eid": entity_id, "et": entity_type},
            ).fetchall()
            return [
                {
                    "propertyDefinitionId": r[0],
                    "name": r[1],
                    "dataType": r[2],
                    "currentValue": r[3] or r[4] or r[5] or r[6],
                }
                for r in rows
            ]
        finally:
            session.close()

    @mcp.tool()
    def SetEntityProperty(
        entity_id: str,
        entity_type: str,
        property_definition_id: str,
        string_value: str | None = None,
        number_value: float | None = None,
        date_value: str | None = None,
        boolean_value: bool | None = None,
        option_id: str | None = None,
        add_option_ids: list[str] | None = None,
        remove_option_ids: list[str] | None = None,
    ) -> dict:
        from datetime import datetime

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        session = _get_session()
        try:
            # For simplicity: single value path
            if add_option_ids or remove_option_ids:
                # Multi-select path (tags)
                for oid in add_option_ids or []:
                    session.execute(
                        text(
                            "INSERT OR IGNORE INTO entity_property_options (entity_id, property_definition_id, option_id, added_at) "
                            "VALUES (:e, :p, :o, :a)"
                        ),
                        {"e": entity_id, "p": property_definition_id, "o": oid, "a": now},
                    )
                for oid in remove_option_ids or []:
                    session.execute(
                        text(
                            "DELETE FROM entity_property_options WHERE entity_id=:e AND property_definition_id=:p AND option_id=:o"
                        ),
                        {"e": entity_id, "p": property_definition_id, "o": oid},
                    )
            else:
                # Single value
                val_text = string_value
                val_num = number_value
                val_date = date_value
                val_bool = 1 if boolean_value else (0 if boolean_value is False else None)
                session.execute(
                    text(
                        """
                        INSERT INTO entity_properties (entity_id, property_definition_id, value_text, value_number, value_date, value_boolean, updated_at)
                        VALUES (:e, :p, :vt, :vn, :vd, :vb, :u)
                        ON CONFLICT(entity_id, property_definition_id) DO UPDATE SET
                          value_text=excluded.value_text,
                          value_number=excluded.value_number,
                          value_date=excluded.value_date,
                          value_boolean=excluded.value_boolean,
                          updated_at=excluded.updated_at
                        """
                    ),
                    {"e": entity_id, "p": property_definition_id, "vt": val_text, "vn": val_num, "vd": val_date, "vb": val_bool, "u": now},
                )
            session.commit()
            return {"ok": True}
        finally:
            session.close()

    @mcp.tool()
    def NameSearch(name: str, matchType: str | None = "partial") -> list[dict]:
        session = _get_session()
        try:
            # Simple FTS
            rows = session.execute(
                text("SELECT entity_id, name FROM search_name_fts WHERE search_name_fts MATCH :q LIMIT 50"),
                {"q": name},
            ).fetchall()
            return [{"entityId": r[0], "name": r[1]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def ContentSearch(query: str, matchType: str | None = "partial") -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text("SELECT entity_id FROM search_content_fts WHERE search_content_fts MATCH :q LIMIT 50"),
                {"q": query},
            ).fetchall()
            return [{"entityId": r[0]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def ReadMetadata(documentId: str) -> dict:
        session = _get_session()
        try:
            row = session.execute(
                text("SELECT e.name, e.entity_type, e.created_at, e.updated_at, d.content_md, d.source, d.is_editable "
                     "FROM entities e LEFT JOIN documents d ON d.entity_id = e.id WHERE e.id = :id"),
                {"id": documentId},
            ).fetchone()
            if not row:
                return {"error": "not found"}
            return {
                "id": documentId,
                "name": row[0],
                "entityType": row[1],
                "createdAt": row[2],
                "updatedAt": row[3],
                "source": row[5] or "native",
                "isEditable": bool(row[6]) if row[6] is not None else True,
                "contentPreview": (row[4] or "")[:200] if row[4] else "",
            }
        finally:
            session.close()

    @mcp.tool()
    def RenameDocument(documentId: str, documentName: str) -> dict:
        session = _get_session()
        try:
            # Production: keep FTS in sync on rename
            session.execute(text("DELETE FROM search_name_fts WHERE entity_id = :id"), {"id": documentId})
            session.execute(text("UPDATE entities SET name = :n, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :id"),
                          {"n": documentName, "id": documentId})
            session.execute(text("INSERT INTO search_name_fts (entity_id, name) VALUES (:e, :n)"), {"e": documentId, "n": documentName})
            session.commit()
            return {"id": documentId, "name": documentName}
        finally:
            session.close()

    @mcp.tool()
    def CreateProject(projectName: str, parentProjectId: str | None = None) -> dict:
        session = _get_session()
        try:
            owner = _get_or_create_demo_user(session)
            eid = _create_entity(session, "project", owner, projectName, parentProjectId)
            # Production: index project name for search
            session.execute(text("INSERT INTO search_name_fts (entity_id, name) VALUES (:e, :n)"), {"e": eid, "n": projectName})
            logger.info("CreateProject created id=%s name=%s", eid, projectName)
            _log_activity(session, owner, "create_project", entity_id=eid)
            session.commit()
            return {"id": eid, "name": projectName, "entityType": "project"}
        finally:
            session.close()

    @mcp.tool()
    def MoveToProject(entityId: str, entityType: str, projectId: str | None = None) -> dict:
        session = _get_session()
        try:
            session.execute(
                text("UPDATE entities SET parent_project_id = :p, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :id"),
                {"p": projectId, "id": entityId}
            )
            session.commit()
            return {"id": entityId, "parentProjectId": projectId}
        finally:
            session.close()

    @mcp.tool()
    def CreateTag(label: str, color: str, scope: str | None = "personal") -> dict:
        import uuid
        from datetime import datetime
        session = _get_session()
        try:
            owner = _get_or_create_demo_user(session)
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            # Find or create the tag property definition (the "set")
            pd_row = session.execute(
                text("SELECT id FROM property_definitions WHERE is_tag=1 AND name = :l LIMIT 1"),
                {"l": label}
            ).fetchone()
            if pd_row:
                pd_id = pd_row[0]
            else:
                pd_id = str(uuid.uuid4())
                session.execute(
                    text("INSERT INTO property_definitions (id, owner_id, name, data_type, is_tag, created_at) "
                         "VALUES (:id, :o, :n, 'multi_select', 1, :c)"),
                    {"id": pd_id, "o": owner, "n": label, "c": now}
                )
            # Create an option for this tag value
            opt_id = str(uuid.uuid4())
            session.execute(
                text("INSERT OR IGNORE INTO property_options (id, property_definition_id, label, color, sort_order) "
                     "VALUES (:id, :pd, :l, :col, 0)"),
                {"id": opt_id, "pd": pd_id, "l": label, "col": color}
            )
            session.commit()
            return {"id": opt_id, "propertyDefinitionId": pd_id, "label": label}
        finally:
            session.close()

    @mcp.tool()
    def ListReminders(completed: bool | None = False, limit: int | None = 20) -> list[dict]:
        session = _get_session()
        try:
            sql = "SELECT r.entity_id, e.name, r.text, r.remind_at, r.completed_at, r.attached_entity_id FROM reminders r JOIN entities e ON e.id = r.entity_id "
            if not completed:
                sql += "WHERE r.completed_at IS NULL "
            else:
                sql += "WHERE r.completed_at IS NOT NULL "
            sql += "ORDER BY r.remind_at LIMIT :lim"
            rows = session.execute(text(sql), {"lim": limit or 20}).fetchall()
            return [
                {"id": r[0], "name": r[1], "text": r[2], "remindAt": r[3], "completedAt": r[4], "attachedEntityId": r[5]}
                for r in rows
            ]
        finally:
            session.close()

    @mcp.tool()
    def CreateReminder(description: str, remindAt: str, entityType: str | None = None, entityId: str | None = None) -> dict:
        session = _get_session()
        try:
            owner = _get_or_create_demo_user(session)
            eid = _create_entity(session, "reminder", owner, description[:80])
            session.execute(
                text("INSERT INTO reminders (entity_id, user_id, text, remind_at, attached_entity_id) VALUES (:e, :u, :t, :ra, :ae)"),
                {"e": eid, "u": owner, "t": description, "ra": remindAt, "ae": entityId}
            )
            logger.info("CreateReminder created id=%s", eid)
            _log_activity(session, owner, "create_reminder", entity_id=eid)
            session.commit()
            return {"id": eid, "text": description, "remindAt": remindAt}
        finally:
            session.close()

    @mcp.tool()
    def UpdateReminder(reminderId: str, completed: bool | None = None, remindAt: str | None = None, description: str | None = None) -> dict:
        session = _get_session()
        try:
            sets = []
            params = {"id": reminderId}
            if completed is not None:
                sets.append("completed_at = CASE WHEN :c THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE NULL END")
                params["c"] = completed
            if remindAt:
                sets.append("remind_at = :ra")
                params["ra"] = remindAt
            if description:
                sets.append("text = :t")
                params["t"] = description
            if sets:
                session.execute(text(f"UPDATE reminders SET {', '.join(sets)} WHERE entity_id = :id"), params)
            session.commit()
            return {"id": reminderId, "updated": True}
        finally:
            session.close()

    @mcp.tool()
    def DeleteReminder(reminderId: str) -> dict:
        session = _get_session()
        try:
            session.execute(text("DELETE FROM reminders WHERE entity_id = :id"), {"id": reminderId})
            session.execute(text("DELETE FROM entities WHERE id = :id"), {"id": reminderId})
            session.commit()
            return {"id": reminderId, "deleted": True}
        finally:
            session.close()

    @mcp.tool()
    def ReadProject(projectId: str) -> dict:
        session = _get_session()
        try:
            children = session.execute(
                text("SELECT id, entity_type, name FROM entities WHERE parent_project_id = :p AND deleted_at IS NULL"),
                {"p": projectId}
            ).fetchall()
            return {
                "id": projectId,
                "contents": [{"id": c[0], "entityType": c[1], "name": c[2]} for c in children]
            }
        finally:
            session.close()

    @mcp.tool()
    def ListInboxes() -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(text("SELECT id, email_address, is_primary, is_delegated FROM inboxes")).fetchall()
            return [{"id": r[0], "emailAddress": r[1], "isPrimary": bool(r[2]), "isDelegated": bool(r[3])} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def SendChannelMessage(channel_id: str, content: str, thread_id: str | None = None) -> dict:
        import uuid
        from datetime import datetime
        session = _get_session()
        try:
            owner = _get_or_create_demo_user(session)
            mid = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            session.execute(
                text("INSERT INTO channel_messages (id, channel_id, parent_message_id, sender_user_id, content, created_at) "
                     "VALUES (:id, :ch, :par, :u, :c, :ca)"),
                {"id": mid, "ch": channel_id, "par": thread_id, "u": owner, "c": content, "ca": now}
            )
            session.commit()
            return {"id": mid, "channelId": channel_id}
        finally:
            session.close()

    @mcp.tool()
    def ReadChat(chatId: str) -> dict:
        session = _get_session()
        try:
            msgs = session.execute(
                text("SELECT role, content, created_at FROM chat_messages WHERE chat_id = :c ORDER BY created_at"),
                {"c": chatId}
            ).fetchall()
            return {"id": chatId, "messages": [{"role": m[0], "content": m[1], "createdAt": m[2]} for m in msgs]}
        finally:
            session.close()

    @mcp.tool()
    def ListBots() -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(text("SELECT id, name, handle, description FROM bots WHERE deleted_at IS NULL")).fetchall()
            return [{"id": r[0], "name": r[1], "handle": r[2], "description": r[3]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def CreateBot(name: str, handle: str, description: str | None = None) -> dict:
        import uuid
        session = _get_session()
        try:
            owner = _get_or_create_demo_user(session)
            bid = str(uuid.uuid4())
            session.execute(
                text("INSERT INTO bots (id, name, handle, owner_user_id, description) VALUES (:id, :n, :h, :o, :d)"),
                {"id": bid, "n": name, "h": handle, "o": owner, "d": description}
            )
            session.commit()
            return {"id": bid, "name": name, "handle": handle}
        finally:
            session.close()

    @mcp.tool()
    def GetThread(threadId: str) -> dict:
        session = _get_session()
        try:
            thread = session.execute(text("SELECT subject FROM email_threads WHERE entity_id = :id"), {"id": threadId}).fetchone()
            msgs = session.execute(
                text("SELECT sender, body, sent_at FROM email_messages WHERE thread_id = :t ORDER BY sent_at"),
                {"t": threadId}
            ).fetchall()
            return {
                "id": threadId,
                "subject": thread[0] if thread else None,
                "messages": [{"sender": m[0], "body": m[1], "sentAt": m[2]} for m in msgs]
            }
        finally:
            session.close()

    @mcp.tool()
    def ListNotifications(limit: int | None = 20) -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text("SELECT id, notif_type, entity_id, seen_at, done_at, created_at FROM notifications ORDER BY created_at DESC LIMIT :l"),
                {"l": limit or 20}
            ).fetchall()
            return [{"id": r[0], "type": r[1], "entityId": r[2], "seenAt": r[3], "doneAt": r[4], "createdAt": r[5]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def MarkNotificationsSeen(notificationIds: list[str]) -> dict:
        session = _get_session()
        try:
            for nid in notificationIds:
                session.execute(text("UPDATE notifications SET seen_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :id"), {"id": nid})
            session.commit()
            return {"updated": len(notificationIds)}
        finally:
            session.close()

    @mcp.tool()
    def MarkNotificationsDone(notificationIds: list[str], done: bool) -> dict:
        session = _get_session()
        try:
            for nid in notificationIds:
                val = "strftime('%Y-%m-%dT%H:%M:%fZ','now')" if done else "NULL"
                session.execute(text(f"UPDATE notifications SET done_at = {val} WHERE id = :id"), {"id": nid})
            session.commit()
            return {"updated": len(notificationIds)}
        finally:
            session.close()

    @mcp.tool()
    def ListCalendarEvents(start: str, end: str) -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text("SELECT id, title, start_at, end_at FROM calendar_events WHERE start_at >= :s AND start_at < :e ORDER BY start_at"),
                {"s": start, "e": end}
            ).fetchall()
            return [{"id": r[0], "title": r[1], "startAt": r[2], "endAt": r[3]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def CreateCalendarEvent(title: str, time: dict) -> dict:
        import uuid
        session = _get_session()
        try:
            owner = _get_or_create_demo_user(session)
            # Use first calendar or create implicit
            cal = session.execute(text("SELECT id FROM calendars LIMIT 1")).fetchone()
            if not cal:
                cal_id = str(uuid.uuid4())
                session.execute(text("INSERT INTO calendars (id, user_id, name, is_primary) VALUES (:id, :u, 'Default', 1)"), {"id": cal_id, "u": owner})
            else:
                cal_id = cal[0]
            eid = str(uuid.uuid4())
            if time.get("kind") == "allDay":
                start = time.get("startDate")
                end = time.get("endDate")
            else:
                start = time.get("startsAt")
                end = time.get("endsAt")
            session.execute(
                text("INSERT INTO calendar_events (id, calendar_id, title, start_at, end_at) VALUES (:id, :c, :t, :s, :e)"),
                {"id": eid, "c": cal_id, "t": title, "s": start, "e": end}
            )
            session.commit()
            return {"id": eid, "title": title}
        finally:
            session.close()

    @mcp.tool()
    def ReadActivity(**kwargs) -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text("SELECT id, action_type, entity_id, property_name, created_at FROM activity_log ORDER BY created_at DESC LIMIT 100")
            ).fetchall()
            return [{"id": r[0], "action": r[1], "entityId": r[2], "property": r[3], "createdAt": r[4]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def BulkSetEntityPropertyOptions(property_definition_id: str, entities: list[dict], add_option_ids: list[str] | None = None, remove_option_ids: list[str] | None = None) -> dict:
        session = _get_session()
        try:
            for ent in entities or []:
                eid = ent.get("entity_id") or ent.get("id")
                if not eid:
                    continue
                for oid in add_option_ids or []:
                    _add_tag_option(session, eid, property_definition_id, oid)
                for oid in remove_option_ids or []:
                    session.execute(
                        text("DELETE FROM entity_property_options WHERE entity_id=:e AND property_definition_id=:p AND option_id=:o"),
                        {"e": eid, "p": property_definition_id, "o": oid}
                    )
            session.commit()
            return {"applied": len(entities or []), "propertyDefinitionId": property_definition_id}
        finally:
            session.close()

    @mcp.tool()
    def EditTag(id: str, property_definition_id: str, label: str | None = None, color: str | None = None) -> dict:
        session = _get_session()
        try:
            sets = []
            p = {"id": id, "pd": property_definition_id}
            if label:
                sets.append("label = :l")
                p["l"] = label
            if color:
                sets.append("color = :c")
                p["c"] = color
            if sets:
                session.execute(text(f"UPDATE property_options SET {', '.join(sets)} WHERE id = :id AND property_definition_id = :pd"), p)
            session.commit()
            return {"id": id, "updated": True}
        finally:
            session.close()

    @mcp.tool()
    def DeleteTag(id: str, property_definition_id: str) -> dict:
        session = _get_session()
        try:
            session.execute(text("DELETE FROM entity_property_options WHERE option_id = :id"), {"id": id})
            session.execute(text("DELETE FROM property_options WHERE id = :id AND property_definition_id = :pd"), {"id": id, "pd": property_definition_id})
            session.commit()
            return {"id": id, "deleted": True}
        finally:
            session.close()

    @mcp.tool()
    def ListCompanies(limit: int | None = 50) -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text("SELECT c.entity_id, e.name, c.domains, c.last_interaction_at FROM companies c JOIN entities e ON e.id=c.entity_id ORDER BY c.last_interaction_at DESC LIMIT :l"),
                {"l": limit or 50}
            ).fetchall()
            return [{"id": r[0], "name": r[1], "domains": r[2], "lastInteractionAt": r[3]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def GetCompany(company_id: str) -> dict:
        session = _get_session()
        try:
            row = session.execute(
                text("SELECT e.name, c.domains FROM companies c JOIN entities e ON e.id = c.entity_id WHERE c.entity_id = :id"),
                {"id": company_id}
            ).fetchone()
            props = session.execute(text("SELECT pd.name, ep.value_text FROM entity_properties ep JOIN property_definitions pd ON pd.id=ep.property_definition_id WHERE ep.entity_id=:id"),
                                   {"id": company_id}).fetchall()
            return {
                "id": company_id,
                "name": row[0] if row else None,
                "domains": row[1] if row else [],
                "properties": {p[0]: p[1] for p in props}
            }
        finally:
            session.close()

    @mcp.tool()
    def ListSkills() -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text("SELECT e.id, e.name, e.updated_at FROM entities e JOIN skill_flags sf ON sf.entity_id = e.id WHERE e.deleted_at IS NULL ORDER BY e.updated_at DESC")
            ).fetchall()
            return [{"id": r[0], "name": r[1], "updatedAt": r[2]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def SearchSkills(name: str) -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text("SELECT e.id, e.name FROM entities e JOIN skill_flags sf ON sf.entity_id=e.id WHERE e.name LIKE :q LIMIT 20"),
                {"q": "%" + name + "%"}
            ).fetchall()
            return [{"id": r[0], "name": r[1]} for r in rows]
        finally:
            session.close()

    @mcp.tool()
    def EditDocument(document_id: str, instructions: str) -> dict:
        """Basic implementation: appends a note with the instructions. For full AI patch use a real LLM or diff engine."""
        session = _get_session()
        try:
            row = session.execute(text("SELECT content_md FROM documents WHERE entity_id = :id"), {"id": document_id}).fetchone()
            current = row[0] if row else ""
            new_content = current + "\n\n<!-- Edit via instructions: " + instructions + " -->\n"
            # Production: keep content FTS in sync
            session.execute(text("DELETE FROM search_content_fts WHERE entity_id = :id"), {"id": document_id})
            session.execute(text("UPDATE documents SET content_md = :c WHERE entity_id = :id"), {"c": new_content, "id": document_id})
            session.execute(text("INSERT INTO search_content_fts (entity_id, content) VALUES (:e, :c)"), {"e": document_id, "c": new_content})
            session.execute(text("UPDATE entities SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :id"), {"id": document_id})
            session.commit()
            return {"id": document_id, "updated": True, "note": "basic append-edit; full patch would apply the instructions"}
        finally:
            session.close()

    @mcp.tool()
    def ReadChannelMessages(channelId: str, windowType: str = "latest", limit: int | None = 25) -> list[dict]:
        session = _get_session()
        try:
            rows = session.execute(
                text("SELECT id, sender_user_id, content, created_at FROM channel_messages WHERE channel_id = :ch ORDER BY created_at DESC LIMIT :l"),
                {"ch": channelId, "l": limit or 25}
            ).fetchall()
            return [{"id": r[0], "sender": r[1], "content": r[2], "createdAt": r[3]} for r in rows]
        finally:
            session.close()

    # --- Stubs for the remaining tools (the long tail: email send, web, code exec, some bot/channel advanced, full import sync etc.) ---

    for t in TOOLS_CATALOG:
        if t["name"] in IMPLEMENTED:
            continue

        def _make_stub(name: str, desc: str):
            def stub(**kwargs: Any) -> dict:
                return {
                    "stub": True,
                    "tool": name,
                    "note": "Handler not fully implemented in this local clone yet. Schema and data model support it. (local-only workspace)",
                    "received": kwargs,
                }
            stub.__name__ = name.replace("/", "_")
            stub.__doc__ = desc
            return stub

        mcp.tool()( _make_stub(t["name"], t.get("description", "")) )


def main() -> None:
    if FastMCP is None:
        print("mcp package not installed. Run: pip install -e '.[mcp]'", file=sys.stderr)
        print("Falling back to printing tool catalog (for inspection).", file=sys.stderr)
        print(json.dumps(TOOLS_CATALOG, indent=2))
        return

    mcp = FastMCP("agent-native-workspace")
    _register_tools(mcp)

    # stdio transport by default (stateless per invocation in host)
    mcp.run()


if __name__ == "__main__":
    main()
