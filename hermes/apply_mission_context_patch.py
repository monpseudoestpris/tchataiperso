"""Patch minimal et reproductible du runtime Hermes pour propager le contexte de mission cLAIr dans MCP `params._meta`."""

from __future__ import annotations

import py_compile
from pathlib import Path

HANDLERS_PATH = Path("/opt/hermes/tools/mcp_tool_handlers.py")
ROUTES_PATH = Path("/opt/hermes/gateway/platforms/api_server_openai_routes.py")


def _replace_once(path: Path, target: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    count = content.count(target)
    if count != 1:
        raise RuntimeError(f"{path}: expected 1 match for target, found {count}:\n{target}")
    path.write_text(content.replace(target, replacement, 1), encoding="utf-8")


def main() -> None:
    # 1. ContextVar + helpers dans mcp_tool_handlers.py
    _replace_once(
        HANDLERS_PATH,
        "import contextvars\n",
        (
            "import contextvars\n\n"
            "_CLAIR_MISSION_CONTEXT: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(\n"
            "    \"clair_mission_context\", default=None\n"
            ")\n\n\n"
            "def set_clair_mission_context(session_id: str | None = None, mission_token: str | None = None) -> None:\n"
            "    sid = (session_id or \"\").strip()\n"
            "    tok = (mission_token or \"\").strip()\n"
            "    if sid or tok:\n"
            "        payload: dict[str, str] = {}\n"
            "        if sid:\n"
            "            payload[\"session_id\"] = sid\n"
            "        if tok:\n"
            "            payload[\"mission_token\"] = tok\n"
            "        _CLAIR_MISSION_CONTEXT.set(payload)\n"
            "    else:\n"
            "        _CLAIR_MISSION_CONTEXT.set(None)\n\n\n"
            "def current_clair_mission_context() -> dict[str, str] | None:\n"
            "    ctx = _CLAIR_MISSION_CONTEXT.get()\n"
            "    return dict(ctx) if isinstance(ctx, dict) and ctx else None\n"
        ),
    )

    # 2. Transmission de meta dans _call_tool_racing_stdio_death
    _replace_once(
        HANDLERS_PATH,
        "async def _call_tool_racing_stdio_death(server, server_name: str, tool_name: str, args: dict, progress_callback=None):",
        "async def _call_tool_racing_stdio_death(server, server_name: str, tool_name: str, args: dict, progress_callback=None, mission_meta: dict[str, str] | None = None):",
    )
    _replace_once(
        HANDLERS_PATH,
        "    extra = {\"progress_callback\": progress_callback} if progress_callback is not None else {}\n"
        "    _call_coro = server.session.call_tool(tool_name, arguments=args, **extra)",
        "    extra = {\"progress_callback\": progress_callback} if progress_callback is not None else {}\n"
        "    if mission_meta:\n"
        "        extra[\"meta\"] = mission_meta\n"
        "    _call_coro = server.session.call_tool(tool_name, arguments=args, **extra)",
    )

    # 3. Capture du contexte sur le thread de l'agent avant bascule sur la boucle MCP
    _replace_once(
        HANDLERS_PATH,
        "        from agent.tool_progress_relay import current_tool_progress\n"
        "        report = current_tool_progress()",
        "        from agent.tool_progress_relay import current_tool_progress\n"
        "        report = current_tool_progress()\n"
        "        mission_meta = current_clair_mission_context()",
    )
    _replace_once(
        HANDLERS_PATH,
        "                    result = await _call_tool_racing_stdio_death(\n"
        "                        server, server_name, tool_name, args, _on_progress if report is not None else None)",
        "                    result = await _call_tool_racing_stdio_death(\n"
        "                        server, server_name, tool_name, args, _on_progress if report is not None else None,\n"
        "                        mission_meta=mission_meta)",
    )

    # 4. Injection du contexte depuis les en-têtes HTTP de /v1/chat/completions
    _replace_once(
        ROUTES_PATH,
        "        if provided_session_id and body.get(\"hermes_notification_category\") == \"diagnostic\":\n"
        "            run_kwargs[\"notification_category\"] = \"diagnostic\"\n"
        "        if stream:",
        "        if provided_session_id and body.get(\"hermes_notification_category\") == \"diagnostic\":\n"
        "            run_kwargs[\"notification_category\"] = \"diagnostic\"\n"
        "        from tools.mcp_tool_handlers import set_clair_mission_context\n"
        "        set_clair_mission_context(\n"
        "            session_id=(provided_session_id or session_id),\n"
        "            mission_token=request.headers.get(\"X-Clair-Mission-Token\", \"\").strip(),\n"
        "        )\n"
        "        if stream:",
    )

    py_compile.compile(str(HANDLERS_PATH), doraise=True)
    py_compile.compile(str(ROUTES_PATH), doraise=True)
    print("Hermes mission context patch applied and compiled successfully.")


if __name__ == "__main__":
    main()
