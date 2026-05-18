"""
lawyer.gftd.ai matter workspace LangGraph — Supervisor + specialist agents.

Topology:
  START → supervisor →
    {matters | grants | hearings | drafting | time_entry}
      → aggregate → END

Registered as assistant_id="lawyer-matter-workspace" in langgraph_server_app.

ADR-2605180600 attorney portal design.
ADR-2605080600 LangGraph Server L3.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

LOG = logging.getLogger("lawyer.matter_workspace")

_FIRM_DID = "did:web:lawyer.gftd.ai"


# ── State ──────────────────────────────────────────────────────────────────────

class LawyerWorkspaceState(TypedDict, total=False):
    # Input
    task_type: str    # "matters" | "grants" | "hearings" | "drafting" | "time_entry" | "unknown"
    lawyer_did: str
    firm_did: str
    matter_id: str
    document_type: str
    content_prompt: str
    jurisdiction: str

    # Supervisor
    routing: str
    routing_reason: str

    # Specialist outputs
    matters: list[dict]
    grants: list[dict]
    hearings: list[dict]
    draft_content: str
    draft_status: str
    time_entries: list[dict]

    # Final
    summary: str
    error: str | None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(tz=_dt.UTC).strftime("%Y-%m-%d %H:%M:%S")


def _query(sql_str: str, params: dict | None = None) -> list[dict]:
    try:
        from sqlalchemy import text
        from pymagatama.db_alchemy import sa_query
        return sa_query(text(sql_str), params or {})
    except Exception as exc:
        LOG.warning("DB query failed: %s", exc)
        return []


def _llm_json(system: str, user: str, max_tokens: int = 400) -> dict:
    try:
        from pymagatama.llm import call_tier
        result = call_tier("structured", system=system, user=user, max_tokens=max_tokens)
        content = result.get("content", "")
        if "```" in content:
            for chunk in content.split("```")[1::2]:
                stripped = chunk.lstrip("json").strip()
                try:
                    return json.loads(stripped)
                except Exception:
                    pass
        try:
            return json.loads(content)
        except Exception:
            return {"raw": content}
    except Exception as exc:
        LOG.warning("LLM JSON call failed: %s", exc)
        return {"error": str(exc)}


# ── Routing map ────────────────────────────────────────────────────────────────

_TASK_TYPE_TO_ROUTING: dict[str, str] = {
    "matters":    "matters",
    "grants":     "grants",
    "hearings":   "hearings",
    "drafting":   "drafting",
    "time_entry": "time_entry",
}

_KEYWORD_ROUTING: list[tuple[list[str], str]] = [
    (["matter", "case", "client", "lead", "counsel"], "matters"),
    (["grant", "invite", "invitation", "accept"],     "grants"),
    (["hearing", "court", "scheduled", "upcoming"],   "hearings"),
    (["draft", "document", "letter", "contract", "agreement", "pleading"], "drafting"),
    (["time", "billing", "hours", "unbilled", "entry"], "time_entry"),
]

_SUPERVISOR_SYSTEM = """You are the routing supervisor for the lawyer.gftd.ai workspace.
Classify the user's task into one of:
  matters     — viewing or searching assigned matters/cases
  grants      — external counsel grant invitations
  hearings    — upcoming court hearings
  drafting    — AI document draft generation
  time_entry  — billing and time tracking

Return JSON: {"routing": "<category>", "reason": "<one sentence>"}
Output ONLY valid JSON, no extra text.
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

def supervisor_node(state: LawyerWorkspaceState) -> dict:
    """Route by task_type if already set; otherwise call LLM classifier."""
    task_type = (state.get("task_type") or "").lower().strip()

    # Direct routing from explicit task_type
    if task_type in _TASK_TYPE_TO_ROUTING:
        routing = _TASK_TYPE_TO_ROUTING[task_type]
        return {"routing": routing, "routing_reason": f"direct task_type: {task_type}"}

    # Keyword fallback
    for keywords, routing in _KEYWORD_ROUTING:
        if any(kw in task_type for kw in keywords):
            return {"routing": routing, "routing_reason": f"keyword match: {keywords[0]}"}

    # LLM classifier (last resort)
    user_msg = f"task_type: {task_type}\nlawyer_did: {state.get('lawyer_did', '')}"
    result = _llm_json(_SUPERVISOR_SYSTEM, user_msg)
    routing = str(result.get("routing", "matters"))
    if routing not in _TASK_TYPE_TO_ROUTING:
        routing = "matters"
    return {
        "routing":        routing,
        "routing_reason": str(result.get("reason", "LLM classification")),
    }


def matters_node(state: LawyerWorkspaceState) -> dict:
    """Fetch active matters for this lawyer."""
    lawyer_did = state.get("lawyer_did", "")
    firm_did = state.get("firm_did", "") or _FIRM_DID
    if not lawyer_did:
        return {"matters": [], "error": "lawyer_did missing"}

    pattern = f"%{lawyer_did}%"
    rows = _query(
        "SELECT matter_id, vertex_id, matter_type, jurisdiction, status, "
        "       lead_advocate_did, co_counsel_dids, client_did, opened_at "
        "FROM vertex_lawfirm_matter "
        "WHERE (lead_advocate_did = :did OR co_counsel_dids LIKE :pattern) "
        "  AND firm_did = :firm_did "
        "ORDER BY opened_at DESC LIMIT 20",
        {"did": lawyer_did, "firm_did": firm_did, "pattern": pattern},
    )

    matters = []
    for row in rows:
        role = "lead" if row.get("lead_advocate_did") == lawyer_did else "coCounsel"
        matters.append({
            "matterId":    row.get("matter_id", ""),
            "matterUri":   row.get("vertex_id", ""),
            "matterType":  row.get("matter_type", ""),
            "jurisdiction": row.get("jurisdiction", ""),
            "status":      row.get("status", ""),
            "role":        role,
            "clientDid":   row.get("client_did", ""),
            "openedAt":    row.get("opened_at", ""),
        })

    LOG.info("matters_node lawyer_did=%s count=%d", lawyer_did, len(matters))
    return {"matters": matters, "error": None}


def grants_node(state: LawyerWorkspaceState) -> dict:
    """Fetch pending (invited) grant records for this lawyer."""
    lawyer_did = state.get("lawyer_did", "")
    if not lawyer_did:
        return {"grants": [], "error": "lawyer_did missing"}

    rows = _query(
        "SELECT vertex_id, grant_id, case_uri, grantee_did, role, status, created_at "
        "FROM vertex_lawfirm_grant "
        "WHERE grantee_did = :did AND status = 'invited' "
        "ORDER BY created_at DESC LIMIT 20",
        {"did": lawyer_did},
    )

    grants = [
        {
            "grantId":   row.get("grant_id", ""),
            "grantUri":  row.get("vertex_id", ""),
            "caseUri":   row.get("case_uri", ""),
            "role":      row.get("role", ""),
            "status":    row.get("status", ""),
            "createdAt": row.get("created_at", ""),
        }
        for row in rows
    ]

    LOG.info("grants_node lawyer_did=%s count=%d", lawyer_did, len(grants))
    return {"grants": grants, "error": None}


def hearings_node(state: LawyerWorkspaceState) -> dict:
    """Fetch upcoming hearings for matters this lawyer is involved in."""
    lawyer_did = state.get("lawyer_did", "")
    firm_did = state.get("firm_did", "") or _FIRM_DID
    if not lawyer_did:
        return {"hearings": [], "error": "lawyer_did missing"}

    pattern = f"%{lawyer_did}%"
    now = _now_iso()

    # Collect relevant matter IDs first
    matter_rows = _query(
        "SELECT matter_id FROM vertex_lawfirm_matter "
        "WHERE (lead_advocate_did = :did OR co_counsel_dids LIKE :pattern) "
        "  AND firm_did = :firm_did AND status != 'closed' LIMIT 50",
        {"did": lawyer_did, "firm_did": firm_did, "pattern": pattern},
    )
    matter_ids = [r.get("matter_id", "") for r in matter_rows if r.get("matter_id")]

    if not matter_ids:
        return {"hearings": [], "error": None}

    in_params: dict = {"now": now}
    in_placeholders = []
    for i, mid in enumerate(matter_ids):
        key = f"mid{i}"
        in_params[key] = mid
        in_placeholders.append(f":{key}")
    in_clause = ", ".join(in_placeholders)

    rows = _query(
        f"SELECT hearing_id, matter_id, hearing_type, scheduled_at, venue, status "
        f"FROM vertex_lawfirm_hearing "
        f"WHERE matter_id IN ({in_clause}) AND scheduled_at > :now "
        f"ORDER BY scheduled_at ASC LIMIT 20",
        in_params,
    )

    hearings = [
        {
            "hearingId":   row.get("hearing_id", ""),
            "matterId":    row.get("matter_id", ""),
            "hearingType": row.get("hearing_type", ""),
            "scheduledAt": row.get("scheduled_at", ""),
            "venue":       row.get("venue", ""),
            "status":      row.get("status", ""),
        }
        for row in rows
    ]

    LOG.info("hearings_node lawyer_did=%s count=%d", lawyer_did, len(hearings))
    return {"hearings": hearings, "error": None}


def drafting_node(state: LawyerWorkspaceState) -> dict:
    """Placeholder — actual drafting delegates to lawyer-document-drafting subgraph."""
    matter_id = state.get("matter_id", "")
    document_type = state.get("document_type", "legal_document")
    jurisdiction = state.get("jurisdiction", "IND")
    content_prompt = state.get("content_prompt", "")

    # Placeholder response; in production, invoke lawyer-document-drafting graph
    draft_content = (
        f"[DRAFTING AGENT]\n"
        f"Document type: {document_type}\n"
        f"Jurisdiction: {jurisdiction}\n"
        f"Matter: {matter_id}\n\n"
        f"Prompt received: {content_prompt[:200]}\n\n"
        f"Use the lawyer-document-drafting assistant for full AI draft generation "
        f"with ISCO-2611 approval gate."
    )

    LOG.info("drafting_node matter_id=%s doc_type=%s", matter_id, document_type)
    return {
        "draft_content": draft_content,
        "draft_status":  "pending_full_graph",
        "error":         None,
    }


def time_entry_node(state: LawyerWorkspaceState) -> dict:
    """Query unbilled time entries for this lawyer."""
    lawyer_did = state.get("lawyer_did", "")
    if not lawyer_did:
        return {"time_entries": [], "error": "lawyer_did missing"}

    rows = _query(
        "SELECT entry_id, matter_id, duration_minutes, created_at "
        "FROM vertex_lawfirm_time_entry "
        "WHERE advocate_did = :did AND billed = false "
        "ORDER BY created_at DESC LIMIT 50",
        {"did": lawyer_did},
    )

    total_minutes = sum(int(r.get("duration_minutes", 0)) for r in rows)
    time_entries = [
        {
            "entryId":         row.get("entry_id", ""),
            "matterId":        row.get("matter_id", ""),
            "durationMinutes": row.get("duration_minutes", 0),
            "createdAt":       row.get("created_at", ""),
        }
        for row in rows
    ]

    LOG.info(
        "time_entry_node lawyer_did=%s entries=%d total_minutes=%d",
        lawyer_did, len(time_entries), total_minutes,
    )
    return {
        "time_entries": time_entries,
        "error":        None,
    }


def aggregate_node(state: LawyerWorkspaceState) -> dict:
    """Combine specialist outputs into a human-readable summary."""
    routing = state.get("routing", "unknown")
    lawyer_did = state.get("lawyer_did", "")
    parts: list[str] = [f"Lawyer workspace summary for {lawyer_did} (routing={routing}):"]

    matters = state.get("matters")
    if matters is not None:
        parts.append(f"  Matters: {len(matters)} found")
        for m in matters[:3]:
            parts.append(
                f"    [{m.get('role', '?')}] {m.get('matterType', '?')} — "
                f"{m.get('status', '?')} ({m.get('jurisdiction', '?')})"
            )

    grants = state.get("grants")
    if grants is not None:
        parts.append(f"  Pending grants: {len(grants)}")
        for g in grants[:3]:
            parts.append(f"    {g.get('grantId', '?')} — {g.get('role', '?')}")

    hearings = state.get("hearings")
    if hearings is not None:
        parts.append(f"  Upcoming hearings: {len(hearings)}")
        for h in hearings[:3]:
            parts.append(
                f"    {h.get('hearingType', '?')} @ {h.get('scheduledAt', '?')} "
                f"({h.get('venue', '?')})"
            )

    draft_content = state.get("draft_content")
    if draft_content:
        parts.append(f"  Draft status: {state.get('draft_status', 'unknown')}")
        parts.append(f"  Draft preview: {draft_content[:120]}...")

    time_entries = state.get("time_entries")
    if time_entries is not None:
        total_min = sum(int(e.get("durationMinutes", 0)) for e in time_entries)
        parts.append(
            f"  Unbilled time: {len(time_entries)} entries, "
            f"{round(total_min / 60, 2)} hours"
        )

    err = state.get("error")
    if err:
        parts.append(f"  Error: {err}")

    return {"summary": "\n".join(parts)}


# ── Graph factory ──────────────────────────────────────────────────────────────

def build_graph():
    """
    Compile the lawyer matter workspace StateGraph.

    Flow:
      supervisor → (routing) →
        {matters | grants | hearings | drafting | time_entry}
          → aggregate → END
    """
    from langgraph.graph import StateGraph, END

    builder = StateGraph(LawyerWorkspaceState)
    builder.add_node("supervisor",   supervisor_node)
    builder.add_node("matters",      matters_node)
    builder.add_node("grants",       grants_node)
    builder.add_node("hearings",     hearings_node)
    builder.add_node("drafting",     drafting_node)
    builder.add_node("time_entry",   time_entry_node)
    builder.add_node("aggregate",    aggregate_node)

    builder.set_entry_point("supervisor")

    def route(state: LawyerWorkspaceState) -> str:
        return state.get("routing", "matters")

    builder.add_conditional_edges(
        "supervisor",
        route,
        {
            "matters":    "matters",
            "grants":     "grants",
            "hearings":   "hearings",
            "drafting":   "drafting",
            "time_entry": "time_entry",
        },
    )

    for node in ("matters", "grants", "hearings", "drafting", "time_entry"):
        builder.add_edge(node, "aggregate")

    builder.add_edge("aggregate", END)

    return builder.compile()


graph = build_graph()

# LangGraph Server registration
GRAPH_CONFIG = {
    "assistant_id": "lawyer-matter-workspace",
    "graph_id":     "lawyer_matter_workspace",
    "description":  (
        "Lawyer matter workspace supervisor — routes to "
        "matters/grants/hearings/drafting/time_entry specialists"
    ),
    "version": "0.1.0",
}
