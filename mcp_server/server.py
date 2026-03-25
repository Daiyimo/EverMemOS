"""
EverMemOS MCP Server
====================
A standalone MCP (Model Context Protocol) server that wraps the EverMemOS REST API.

Exposes the following tools to MCP clients (Claude Code, Cursor, Windsurf, etc.):
  - memorize        : Store a message/conversation turn into long-term memory
  - search_memory   : Semantic / hybrid / agentic search over stored memories
  - fetch_memories  : Fetch memories by type and filters (episodic, profile, etc.)
  - get_user_profile: Retrieve the structured user profile

Usage:
  # Stdio mode (Claude Code MCP)
  python server.py

  # HTTP mode (remote / browser plugin)
  python server.py --transport http --port 3456

Environment variables (can also be in .env):
  EVERMEMOS_BASE_URL  – base URL of the EverMemOS REST API  (default: http://localhost:1995)
  EVERMEMOS_USER_ID   – default user_id injected into requests (default: default_user)
  EVERMEMOS_GROUP_ID  – default group_id injected into requests (default: default_group)
  MCP_PORT            – HTTP transport port (default: 3456)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("evermemos-mcp")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL: str = os.getenv("EVERMEMOS_BASE_URL", "http://localhost:1995").rstrip("/")
DEFAULT_USER_ID: str = os.getenv("EVERMEMOS_USER_ID", "default_user")
DEFAULT_GROUP_ID: str = os.getenv("EVERMEMOS_GROUP_ID", "default_group")
API_PREFIX: str = "/api/v1/memories"

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=60.0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="EverMemOS",
    description=(
        "Long-term memory service for AI agents. "
        "Store, search, and retrieve persistent memories across sessions."
    ),
)

# ---------------------------------------------------------------------------
# Tool: memorize
# ---------------------------------------------------------------------------


@mcp.tool()
def memorize(
    content: str,
    role: str = "user",
    sender_name: str = "",
    user_id: str = "",
    group_id: str = "",
    message_id: str = "",
) -> str:
    """Store a message or conversation turn into long-term memory.

    Args:
        content: The text content to memorize (required).
        role: Message role – "user" or "assistant" (default: "user").
        sender_name: Human-readable name of the sender (optional).
        user_id: Override the default user identity (optional).
        group_id: Override the default conversation group (optional).
        message_id: Idempotency key; auto-generated if omitted (optional).

    Returns:
        JSON string with the memorize result or an error description.
    """
    uid = user_id or DEFAULT_USER_ID
    gid = group_id or DEFAULT_GROUP_ID
    mid = message_id or f"msg_{uuid4().hex[:12]}"
    name = sender_name or uid

    payload = {
        "message_id": mid,
        "create_time": _now_iso(),
        "sender": uid,
        "sender_name": name,
        "role": role,
        "content": content,
        "group_id": gid,
        "group_name": gid,
    }

    try:
        with _client() as client:
            resp = client.post(API_PREFIX, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("memorize OK | user=%s mid=%s", uid, mid)
            return json.dumps(data, ensure_ascii=False, indent=2)
    except httpx.HTTPStatusError as exc:
        msg = f"EverMemOS API error {exc.response.status_code}: {exc.response.text}"
        logger.error(msg)
        return json.dumps({"error": msg})
    except Exception as exc:  # noqa: BLE001
        msg = f"memorize failed: {exc}"
        logger.error(msg)
        return json.dumps({"error": msg})


# ---------------------------------------------------------------------------
# Tool: search_memory
# ---------------------------------------------------------------------------


@mcp.tool()
def search_memory(
    query: str,
    user_id: str = "",
    group_id: str = "",
    retrieve_method: str = "hybrid",
    memory_types: str = "episodic_memory",
    limit: int = 10,
) -> str:
    """Search long-term memories using keyword, vector, hybrid, or agentic retrieval.

    Args:
        query: Natural-language question or keyword to search for (required).
        user_id: Scope search to this user (optional, uses default).
        group_id: Scope search to this group / conversation (optional).
        retrieve_method: One of "keyword", "vector", "hybrid", "rrf", "agentic".
                         "hybrid" is the best general-purpose choice (default).
        memory_types: Comma-separated memory types to search.
                      Options: episodic_memory, event_log, foresight.
                      Default: "episodic_memory".
        limit: Max number of results to return (default: 10).

    Returns:
        JSON string with matching memory records.
    """
    uid = user_id or DEFAULT_USER_ID
    gid = group_id or DEFAULT_GROUP_ID
    types = [t.strip() for t in memory_types.split(",") if t.strip()]

    payload: dict[str, Any] = {
        "query": query,
        "user_id": uid,
        "retrieve_method": retrieve_method,
        "memory_types": types,
        "limit": limit,
    }
    if gid:
        payload["group_id"] = gid

    try:
        with _client() as client:
            resp = client.get(f"{API_PREFIX}/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "search_memory OK | query=%r method=%s results=%s",
                query[:60],
                retrieve_method,
                len(data) if isinstance(data, list) else "?",
            )
            return json.dumps(data, ensure_ascii=False, indent=2)
    except httpx.HTTPStatusError as exc:
        msg = f"EverMemOS API error {exc.response.status_code}: {exc.response.text}"
        logger.error(msg)
        return json.dumps({"error": msg})
    except Exception as exc:  # noqa: BLE001
        msg = f"search_memory failed: {exc}"
        logger.error(msg)
        return json.dumps({"error": msg})


# ---------------------------------------------------------------------------
# Tool: fetch_memories
# ---------------------------------------------------------------------------


@mcp.tool()
def fetch_memories(
    user_id: str = "",
    group_id: str = "",
    memory_type: str = "episodic_memory",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """Fetch stored memories by type without a search query.

    Useful for browsing recent memories or loading context at session start.

    Args:
        user_id: Filter by user identity (optional, uses default).
        group_id: Filter by conversation group (optional).
        memory_type: One of "episodic_memory", "user_profile", "group_profile",
                     "event_log", "foresight", "memcell" (default: "episodic_memory").
        limit: Number of records to return (default: 20).
        offset: Pagination offset (default: 0).

    Returns:
        JSON string with the list of memory records.
    """
    uid = user_id or DEFAULT_USER_ID
    gid = group_id or DEFAULT_GROUP_ID

    params: dict[str, Any] = {
        "user_id": uid,
        "memory_type": memory_type,
        "limit": limit,
        "offset": offset,
    }
    if gid:
        params["group_id"] = gid

    try:
        with _client() as client:
            resp = client.get(API_PREFIX, params=params)
            resp.raise_for_status()
            data = resp.json()
            logger.info("fetch_memories OK | type=%s user=%s", memory_type, uid)
            return json.dumps(data, ensure_ascii=False, indent=2)
    except httpx.HTTPStatusError as exc:
        msg = f"EverMemOS API error {exc.response.status_code}: {exc.response.text}"
        logger.error(msg)
        return json.dumps({"error": msg})
    except Exception as exc:  # noqa: BLE001
        msg = f"fetch_memories failed: {exc}"
        logger.error(msg)
        return json.dumps({"error": msg})


# ---------------------------------------------------------------------------
# Tool: get_user_profile
# ---------------------------------------------------------------------------


@mcp.tool()
def get_user_profile(user_id: str = "", group_id: str = "") -> str:
    """Retrieve the structured profile for a user, including preferences, habits, and key facts.

    Args:
        user_id: The user whose profile to retrieve (optional, uses default).
        group_id: Optional group context (optional).

    Returns:
        JSON string with the user profile.
    """
    uid = user_id or DEFAULT_USER_ID
    gid = group_id or DEFAULT_GROUP_ID

    params: dict[str, Any] = {
        "user_id": uid,
        "memory_type": "user_profile",
        "limit": 1,
    }
    if gid:
        params["group_id"] = gid

    try:
        with _client() as client:
            resp = client.get(API_PREFIX, params=params)
            resp.raise_for_status()
            data = resp.json()
            logger.info("get_user_profile OK | user=%s", uid)
            return json.dumps(data, ensure_ascii=False, indent=2)
    except httpx.HTTPStatusError as exc:
        msg = f"EverMemOS API error {exc.response.status_code}: {exc.response.text}"
        logger.error(msg)
        return json.dumps({"error": msg})
    except Exception as exc:  # noqa: BLE001
        msg = f"get_user_profile failed: {exc}"
        logger.error(msg)
        return json.dumps({"error": msg})


# ---------------------------------------------------------------------------
# Tool: health_check
# ---------------------------------------------------------------------------


@mcp.tool()
def health_check() -> str:
    """Check if the EverMemOS backend is reachable and healthy.

    Returns:
        JSON string with health status.
    """
    try:
        with _client() as client:
            resp = client.get("/health", timeout=10.0)
            resp.raise_for_status()
            return json.dumps({"status": "ok", "response": resp.json()})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "detail": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="EverMemOS MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: 'stdio' for Claude Code / desktop clients (default), "
             "'http' for remote / browser plugin access",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "3456")),
        help="HTTP transport port (default: 3456, or $MCP_PORT)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="HTTP transport bind host (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    logger.info(
        "Starting EverMemOS MCP Server | transport=%s backend=%s",
        args.transport,
        BASE_URL,
    )

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
