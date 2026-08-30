from __future__ import annotations

"""
Attorney portal workspace primitives — LangServer handlers.

Task types:
  lawyer.dashboard.get        Fetch lawyer dashboard snapshot
  lawyer.matters.list         List assigned matters (lead + coCounsel)
  lawyer.grants.list          List pending externalCounselGrant records
  lawyer.grant.accept         Accept a grant invitation
  lawyer.work_note.log        Log encrypted work note + optional time entry
  lawyer.document_draft.submit  Trigger AI draft generation + ISCO-2611 review gate

ADR-2605180600 lawyer attorney portal.
ADR-0018 PII Tier 3 — work notes are signal:v1: field-encrypted.
ADR-0016 legal cluster — ISCO-2611 lawyer approval required for AI drafts.

Tables used:
  vertex_lawfirm_matter     (shared, read-only from lawyer)
  vertex_lawfirm_grant      (shared, write accepted_at)
  vertex_lawfirm_hearing    (shared, read-only)
  vertex_lawfirm_time_entry (shared, write as firmDid=lawyer)
  vertex_lawyer_work_note   (lawyer-own)
  vertex_lawyer_document_draft (lawyer-own)
"""

import datetime as _dt
import json
import logging
import uuid
from typing import Any

LOG = logging.getLogger("lawyer.workspace")

_FIRM_DID = "did:web:lawyer.gftd.ai"
_OWNER_DID = "did:web:bpmn.gftd.ai"


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.UTC).strftime("%Y-%m-%d %H:%M:%S")


def _vid(kind: str) -> str:
    stamp = _dt.datetime.now(tz=_dt.UTC).strftime("%Y%m%d%H%M%S")
    return f"at://did:web:lawyer.gftd.ai/ai.gftd.apps.lawyer.{kind}/{stamp}-{uuid.uuid4().hex[:8]}"


def _enc_field(plaintext: str) -> str:
    """App-layer field encryption placeholder.
    Production: signal:v1: prefix + AES-GCM with advocate-held key.
    Day-0 dev: base64-wrapped (signal:v1 wiring is parallel work in adjacent
    primitive). Mark with prefix so consumers know to decrypt."""
    if not plaintext:
        return ""
    import base64
    return f"signal:v1:{base64.b64encode(plaintext.encode()).decode()}"


def _execute(sql_str: str, params: dict) -> bool:
    try:
        from sqlalchemy import text
        from pymagatama.db_alchemy import sa_rowcount
        sa_rowcount(text(sql_str), params)
        return True
    except Exception as exc:
        LOG.warning("execute failed: %s", exc)
        return False


def _query(sql_str: str, params: dict | None = None) -> list[dict]:
    try:
        from sqlalchemy import text
        from pymagatama.db_alchemy import sa_query
        return sa_query(text(sql_str), params or {})
    except Exception as exc:
        LOG.warning("query failed: %s", exc)
        return []


# ── Task: lawyer.dashboard.get ────────────────────────────────────────────────

async def task_lawyer_dashboard_get(
    lawyer_did: str = "",
    firm_did: str = "",
) -> dict:
    if not lawyer_did:
        return {"ok": False, "error": "lawyer_did required"}

    firm_did = firm_did or _FIRM_DID
    pattern = f"%{lawyer_did}%"

    # Active matters (lead or co-counsel)
    matter_rows = _query(
        "SELECT matter_id, vertex_id, matter_type, jurisdiction, status, "
        "       lead_advocate_did, co_counsel_dids, client_did, opened_at "
        "FROM vertex_lawfirm_matter "
        "WHERE (lead_advocate_did = :did OR co_counsel_dids LIKE :pattern) "
        "  AND status != 'closed' "
        "ORDER BY opened_at DESC LIMIT 100",
        {"did": lawyer_did, "pattern": pattern},
    )
    active_matters = len(matter_rows)
    recent_matters = []
    for row in matter_rows[:5]:
        role = "lead" if row.get("lead_advocate_did") == lawyer_did else "coCounsel"
        recent_matters.append({
            "matterId":   row.get("matter_id", ""),
            "matterUri":  row.get("vertex_id", ""),
            "matterType": row.get("matter_type", ""),
            "jurisdiction": row.get("jurisdiction", ""),
            "status":     row.get("status", ""),
            "role":       role,
            "clientDid":  row.get("client_did", ""),
            "openedAt":   row.get("opened_at", ""),
        })

    # Pending grants (invited)
    grant_rows = _query(
        "SELECT vertex_id, grant_id, case_uri, grantee_did, role, status, created_at "
        "FROM vertex_lawfirm_grant "
        "WHERE grantee_did = :did AND status = 'invited' "
        "ORDER BY created_at DESC LIMIT 20",
        {"did": lawyer_did},
    )
    pending_grants = len(grant_rows)
    pending_grant_list = [
        {
            "grantId":   row.get("grant_id", ""),
            "grantUri":  row.get("vertex_id", ""),
            "caseUri":   row.get("case_uri", ""),
            "role":      row.get("role", ""),
            "status":    row.get("status", ""),
            "createdAt": row.get("created_at", ""),
        }
        for row in grant_rows[:5]
    ]

    # Upcoming hearings — matters where this lawyer is involved
    matter_ids = [r.get("matter_id", "") for r in matter_rows if r.get("matter_id")]
    hearing_rows: list[dict] = []
    if matter_ids:
        # Build a safe IN-clause with individual params
        in_params: dict = {"did": lawyer_did, "now": _now_iso()}
        in_placeholders = []
        for i, mid in enumerate(matter_ids[:50]):  # cap at 50 to avoid giant query
            key = f"mid{i}"
            in_params[key] = mid
            in_placeholders.append(f":{key}")
        in_clause = ", ".join(in_placeholders)
        hearing_rows = _query(
            f"SELECT hearing_id, matter_id, hearing_type, scheduled_at, venue, status "
            f"FROM vertex_lawfirm_hearing "
            f"WHERE matter_id IN ({in_clause}) "
            f"  AND scheduled_at > :now "
            f"ORDER BY scheduled_at ASC LIMIT 20",
            in_params,
        )
    upcoming_hearings = len(hearing_rows)
    hearing_list = [
        {
            "hearingId":   row.get("hearing_id", ""),
            "matterId":    row.get("matter_id", ""),
            "hearingType": row.get("hearing_type", ""),
            "scheduledAt": row.get("scheduled_at", ""),
            "venue":       row.get("venue", ""),
            "status":      row.get("status", ""),
        }
        for row in hearing_rows[:5]
    ]

    # Unbilled time entries
    time_rows = _query(
        "SELECT COALESCE(SUM(duration_minutes), 0) AS total_minutes "
        "FROM vertex_lawfirm_time_entry "
        "WHERE advocate_did = :did AND billed = false",
        {"did": lawyer_did},
    )
    raw_minutes = int(time_rows[0].get("total_minutes", 0)) if time_rows else 0
    unbilled_hours = round(raw_minutes / 60, 2)

    LOG.info(
        "dashboard lawyer_did=%s active_matters=%d pending_grants=%d unbilled_hours=%.2f",
        lawyer_did, active_matters, pending_grants, unbilled_hours,
    )
    return {
        "ok":               True,
        "lawyerDid":        lawyer_did,
        "activeMatters":    active_matters,
        "pendingGrants":    pending_grants,
        "upcomingHearings": upcoming_hearings,
        "unbilledHours":    unbilled_hours,
        "recentMatters":    recent_matters,
        "pendingGrantList": pending_grant_list,
        "hearingList":      hearing_list,
    }


# ── Task: lawyer.matters.list ─────────────────────────────────────────────────

async def task_lawyer_matters_list(
    lawyer_did: str = "",
    firm_did: str = "",
    status: str = "",
    role: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    if not lawyer_did:
        return {"ok": False, "error": "lawyer_did required"}

    firm_did = firm_did or _FIRM_DID
    limit = max(1, min(limit, 100))
    pattern = f"%{lawyer_did}%"

    params: dict = {
        "did":      lawyer_did,
        "firm_did": firm_did,
        "pattern":  pattern,
        "limit":    limit,
        "offset":   offset,
    }

    # Build WHERE clause
    base_where = (
        "(lead_advocate_did = :did OR co_counsel_dids LIKE :pattern) "
        "AND firm_did = :firm_did"
    )
    if status:
        base_where += " AND status = :status"
        params["status"] = status
    if role == "lead":
        base_where += " AND lead_advocate_did = :did"
    elif role == "coCounsel":
        # already in base_where; narrow to co-counsel only
        base_where = (
            "co_counsel_dids LIKE :pattern "
            "AND lead_advocate_did != :did "
            "AND firm_did = :firm_did"
        )
        if status:
            base_where += " AND status = :status"

    rows = _query(
        f"SELECT matter_id, vertex_id, matter_type, jurisdiction, status, "
        f"       lead_advocate_did, co_counsel_dids, client_did, opened_at "
        f"FROM vertex_lawfirm_matter "
        f"WHERE {base_where} "
        f"ORDER BY opened_at DESC LIMIT :limit OFFSET :offset",
        params,
    )

    count_rows = _query(
        f"SELECT COUNT(*) AS total FROM vertex_lawfirm_matter WHERE {base_where}",
        params,
    )
    total = int(count_rows[0].get("total", 0)) if count_rows else len(rows)

    matters = []
    for row in rows:
        inferred_role = "lead" if row.get("lead_advocate_did") == lawyer_did else "coCounsel"
        matters.append({
            "matterId":    row.get("matter_id", ""),
            "matterUri":   row.get("vertex_id", ""),
            "matterType":  row.get("matter_type", ""),
            "jurisdiction": row.get("jurisdiction", ""),
            "status":      row.get("status", ""),
            "role":        inferred_role,
            "clientDid":   row.get("client_did", ""),
            "openedAt":    row.get("opened_at", ""),
        })

    LOG.info("matters.list lawyer_did=%s count=%d total=%d", lawyer_did, len(matters), total)
    return {
        "ok":      True,
        "matters": matters,
        "total":   total,
        "offset":  offset,
        "limit":   limit,
    }


# ── Task: lawyer.grants.list ──────────────────────────────────────────────────

async def task_lawyer_grants_list(
    lawyer_did: str = "",
    status: str = "invited",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    if not lawyer_did:
        return {"ok": False, "error": "lawyer_did required"}

    limit = max(1, min(limit, 100))
    params: dict = {
        "did":    lawyer_did,
        "status": status or "invited",
        "limit":  limit,
        "offset": offset,
    }

    rows = _query(
        "SELECT vertex_id, grant_id, case_uri, grantee_did, grantee_handle, "
        "       lead_bengoshi_hint, role, status, expires_at, created_at "
        "FROM vertex_lawfirm_grant "
        "WHERE grantee_did = :did AND status = :status "
        "ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
        params,
    )

    count_rows = _query(
        "SELECT COUNT(*) AS total FROM vertex_lawfirm_grant "
        "WHERE grantee_did = :did AND status = :status",
        params,
    )
    total = int(count_rows[0].get("total", 0)) if count_rows else len(rows)

    grants = [
        {
            "grantId":         row.get("grant_id", ""),
            "grantUri":        row.get("vertex_id", ""),
            "caseUri":         row.get("case_uri", ""),
            "granteeDid":      row.get("grantee_did", ""),
            "granteeHandle":   row.get("grantee_handle", ""),
            "leadBengoshiHint": row.get("lead_bengoshi_hint", ""),
            "role":            row.get("role", ""),
            "status":          row.get("status", ""),
            "expiresAt":       row.get("expires_at", ""),
            "createdAt":       row.get("created_at", ""),
        }
        for row in rows
    ]

    LOG.info("grants.list lawyer_did=%s status=%s count=%d", lawyer_did, status, len(grants))
    return {
        "ok":     True,
        "grants": grants,
        "total":  total,
        "offset": offset,
        "limit":  limit,
    }


# ── Task: lawyer.grant.accept ─────────────────────────────────────────────────

async def task_lawyer_grant_accept(
    grant_did: str = "",
    lawyer_did: str = "",
    acceptance_note: str = "",
) -> dict:
    if not grant_did or not lawyer_did:
        return {"ok": False, "error": "grant_did and lawyer_did required"}

    # Verify grant exists and belongs to this lawyer
    grant_rows = _query(
        "SELECT vertex_id, grant_id, case_uri, grantee_did, role, status "
        "FROM vertex_lawfirm_grant "
        "WHERE vertex_id = :grant_did AND grantee_did = :lawyer_did",
        {"grant_did": grant_did, "lawyer_did": lawyer_did},
    )
    if not grant_rows:
        return {"ok": False, "error": "Grant not found or already processed"}

    grant = grant_rows[0]
    if grant.get("status") != "invited":
        return {"ok": False, "error": "Grant not found or already processed"}

    now = _now_iso()
    case_uri = grant.get("case_uri", "")

    # Accept the grant
    _execute(
        "UPDATE vertex_lawfirm_grant "
        "SET status = 'accepted', accepted_at = :now "
        "WHERE vertex_id = :grant_did",
        {"now": now, "grant_did": grant_did},
    )

    # Log acceptance note if provided
    note_uri = ""
    if acceptance_note:
        note_uri = _vid("workNote")
        note_id = note_uri.rsplit("/", 1)[-1]
        matter_id = case_uri.rsplit("/", 1)[-1] if case_uri else ""
        _execute(
            "INSERT INTO vertex_lawyer_work_note "
            "(vertex_id, note_id, matter_id, note_type, content_cipher, "
            " billable_minutes, tags_json, lawyer_did, firm_did, created_at, owner_did) "
            "VALUES (:vid, :nid, :mid, 'acceptance_note', :cc, "
            " 0, :tags, :ldid, :fdid, :now, :owner)",
            {
                "vid":   note_uri,
                "nid":   note_id,
                "mid":   matter_id,
                "cc":    _enc_field(acceptance_note[:4000]),
                "tags":  json.dumps(["grant_acceptance"]),
                "ldid":  lawyer_did,
                "fdid":  _FIRM_DID,
                "now":   now,
                "owner": _OWNER_DID,
            },
        )

    # Derive matter_id from case_uri for workspace link
    matter_id_for_url = case_uri.rsplit("/", 1)[-1] if case_uri else grant.get("grant_id", "")

    LOG.info("grant.accept grant_did=%s lawyer_did=%s", grant_did, lawyer_did)
    return {
        "ok":           True,
        "grantDid":     grant_did,
        "matterDid":    case_uri,
        "status":       "accepted",
        "workspaceUri": f"/matters/{matter_id_for_url}",
        "noteUri":      note_uri,
    }


# ── Task: lawyer.work_note.log ────────────────────────────────────────────────

async def task_lawyer_work_note_log(
    lawyer_did: str = "",
    firm_did: str = "",
    matter_id: str = "",
    note_type: str = "general",
    content: str = "",
    billable_minutes: int = 0,
    tags: list[str] | None = None,
) -> dict:
    if not matter_id:
        return {"ok": False, "error": "matter_id required"}
    if not content:
        return {"ok": False, "error": "content required"}
    if not lawyer_did:
        return {"ok": False, "error": "lawyer_did required"}

    firm_did = firm_did or _FIRM_DID
    tags = tags or []
    now = _now_iso()

    note_uri = _vid("workNote")
    note_id = note_uri.rsplit("/", 1)[-1]

    _execute(
        "INSERT INTO vertex_lawyer_work_note "
        "(vertex_id, note_id, matter_id, note_type, content_cipher, "
        " billable_minutes, tags_json, lawyer_did, firm_did, created_at, owner_did) "
        "VALUES (:vid, :nid, :mid, :nt, :cc, "
        " :bm, :tags, :ldid, :fdid, :now, :owner)",
        {
            "vid":   note_uri,
            "nid":   note_id,
            "mid":   matter_id,
            "nt":    note_type[:100],
            "cc":    _enc_field(content[:8000]),
            "bm":    max(0, int(billable_minutes)),
            "tags":  json.dumps(tags[:20], ensure_ascii=False),
            "ldid":  lawyer_did,
            "fdid":  firm_did,
            "now":   now,
            "owner": _OWNER_DID,
        },
    )

    time_entry_uri = ""
    if billable_minutes and billable_minutes > 0:
        time_entry_uri = _vid("timeEntry")
        te_id = time_entry_uri.rsplit("/", 1)[-1]
        _execute(
            "INSERT INTO vertex_lawfirm_time_entry "
            "(vertex_id, entry_id, matter_id, advocate_did, firm_did, "
            " duration_minutes, note_uri, billed, created_at, owner_did) "
            "VALUES (:vid, :eid, :mid, :adid, :fdid, "
            " :dur, :nuri, false, :now, :owner)",
            {
                "vid":   time_entry_uri,
                "eid":   te_id,
                "mid":   matter_id,
                "adid":  lawyer_did,
                "fdid":  firm_did,
                "dur":   int(billable_minutes),
                "nuri":  note_uri,
                "now":   now,
                "owner": _OWNER_DID,
            },
        )

    LOG.info(
        "work_note.log note_id=%s matter_id=%s billable_minutes=%d",
        note_id, matter_id, billable_minutes,
    )
    result: dict = {
        "ok":      True,
        "noteId":  note_id,
        "noteUri": note_uri,
    }
    if time_entry_uri:
        result["timeEntryUri"] = time_entry_uri
    return result


# ── Task: lawyer.document_draft.submit ───────────────────────────────────────

async def task_lawyer_document_draft_submit(
    lawyer_did: str = "",
    firm_did: str = "",
    matter_id: str = "",
    document_type: str = "",
    title_hint: str = "",
    content_prompt: str = "",
    jurisdiction: str = "",
    reviewer_did: str = "",
) -> dict:
    if not lawyer_did:
        return {"ok": False, "error": "lawyer_did required"}
    if not matter_id:
        return {"ok": False, "error": "matter_id required"}
    if not document_type:
        return {"ok": False, "error": "document_type required"}
    if not content_prompt:
        return {"ok": False, "error": "content_prompt required"}

    firm_did = firm_did or _FIRM_DID
    jurisdiction = jurisdiction or "IND"
    now = _now_iso()

    # Generate AI draft (placeholder; wired via LangGraph in production)
    generated_content = (
        f"[AI DRAFT — {document_type} for {jurisdiction}]\n\n"
        f"Based on: {content_prompt[:200]}\n\n"
        f"[ISCO-2611 review required before use]"
    )

    # Try LLM call if available
    try:
        from pymagatama.llm import call_tier
        result = call_tier(
            "balanced",
            system=(
                f"You are a legal document drafting assistant. "
                f"Generate a {document_type} for {jurisdiction} jurisdiction. "
                f"The document must be professional, legally precise, and comply "
                f"with {jurisdiction} bar rules. "
                f"IMPORTANT: Add a disclaimer that this is an AI-generated draft "
                f"requiring review by a licensed advocate (ISCO-2611) before use."
            ),
            user=(
                f"{content_prompt}\n\n"
                f"Document type: {document_type}\n"
                f"Jurisdiction: {jurisdiction}"
            ),
            max_tokens=2400,
        )
        llm_text = str(result.get("content", "")).strip()
        if llm_text:
            generated_content = llm_text
    except Exception as exc:
        LOG.info("LLM call skipped or failed (using placeholder): %s", exc)

    draft_uri = _vid("documentDraft")
    draft_id = draft_uri.rsplit("/", 1)[-1]
    title = title_hint or f"{document_type} — {jurisdiction} — {now[:10]}"

    _execute(
        "INSERT INTO vertex_lawyer_document_draft "
        "(vertex_id, draft_id, matter_id, document_type, title, "
        " content_cipher, status, reviewer_did, reviewed_at, review_notes, "
        " lawyer_did, firm_did, submitted_at, created_at, owner_did) "
        "VALUES (:vid, :did, :mid, :dt, :title, "
        " :cc, 'under_review', :rdid, '', '', "
        " :ldid, :fdid, :now, :now, :owner)",
        {
            "vid":   draft_uri,
            "did":   draft_id,
            "mid":   matter_id,
            "dt":    document_type[:200],
            "title": title[:500],
            "cc":    _enc_field(generated_content),
            "rdid":  reviewer_did,
            "ldid":  lawyer_did,
            "fdid":  firm_did,
            "now":   now,
            "owner": _OWNER_DID,
        },
    )

    LOG.info(
        "document_draft.submit draft_id=%s matter_id=%s doc_type=%s reviewer=%s",
        draft_id, matter_id, document_type, reviewer_did,
    )
    return {
        "ok":              True,
        "draftId":         draft_id,
        "draftUri":        draft_uri,
        "status":          "under_review",
        "reviewerDid":     reviewer_did,
        "generatedContent": generated_content,
    }


# ── Worker registration ───────────────────────────────────────────────────────

def register(app: Any, timeout_ms: int = 60_000) -> None:
    from pymagatama.langserver_compat import LangServerWorker
    if not isinstance(app, LangServerWorker):
        return

    @app.task(task_type="lawyer.dashboard.get",
              timeout_ms=timeout_ms, max_jobs_to_activate=8)
    async def _dashboard(lawyer_did: str = "", firm_did: str = "") -> dict:
        return await task_lawyer_dashboard_get(
            lawyer_did=lawyer_did, firm_did=firm_did,
        )

    @app.task(task_type="lawyer.matters.list",
              timeout_ms=timeout_ms, max_jobs_to_activate=8)
    async def _matters_list(
        lawyer_did: str = "", firm_did: str = "",
        status: str = "", role: str = "",
        limit: int = 20, offset: int = 0,
    ) -> dict:
        return await task_lawyer_matters_list(
            lawyer_did=lawyer_did, firm_did=firm_did,
            status=status, role=role, limit=limit, offset=offset,
        )

    @app.task(task_type="lawyer.grants.list",
              timeout_ms=timeout_ms, max_jobs_to_activate=8)
    async def _grants_list(
        lawyer_did: str = "", status: str = "invited",
        limit: int = 20, offset: int = 0,
    ) -> dict:
        return await task_lawyer_grants_list(
            lawyer_did=lawyer_did, status=status, limit=limit, offset=offset,
        )

    @app.task(task_type="lawyer.grant.accept",
              timeout_ms=timeout_ms, max_jobs_to_activate=4)
    async def _grant_accept(
        grant_did: str = "", lawyer_did: str = "",
        acceptance_note: str = "",
    ) -> dict:
        return await task_lawyer_grant_accept(
            grant_did=grant_did, lawyer_did=lawyer_did,
            acceptance_note=acceptance_note,
        )

    @app.task(task_type="lawyer.work_note.log",
              timeout_ms=timeout_ms, max_jobs_to_activate=8)
    async def _work_note_log(
        lawyer_did: str = "", firm_did: str = "",
        matter_id: str = "", note_type: str = "general",
        content: str = "", billable_minutes: int = 0,
        tags: list[str] | None = None,
    ) -> dict:
        return await task_lawyer_work_note_log(
            lawyer_did=lawyer_did, firm_did=firm_did,
            matter_id=matter_id, note_type=note_type,
            content=content, billable_minutes=billable_minutes,
            tags=tags or [],
        )

    @app.task(task_type="lawyer.document_draft.submit",
              timeout_ms=max(timeout_ms, 120_000), max_jobs_to_activate=2)
    async def _document_draft_submit(
        lawyer_did: str = "", firm_did: str = "",
        matter_id: str = "", document_type: str = "",
        title_hint: str = "", content_prompt: str = "",
        jurisdiction: str = "", reviewer_did: str = "",
    ) -> dict:
        return await task_lawyer_document_draft_submit(
            lawyer_did=lawyer_did, firm_did=firm_did,
            matter_id=matter_id, document_type=document_type,
            title_hint=title_hint, content_prompt=content_prompt,
            jurisdiction=jurisdiction, reviewer_did=reviewer_did,
        )

    LOG.info(
        "Registered tasks: lawyer.dashboard.get, lawyer.matters.list, "
        "lawyer.grants.list, lawyer.grant.accept, "
        "lawyer.work_note.log, lawyer.document_draft.submit"
    )
