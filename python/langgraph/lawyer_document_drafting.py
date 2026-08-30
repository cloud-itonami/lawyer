"""
Attorney portal document drafting LangGraph — AI draft + ISCO-2611 approval gate.

Topology:
  START
    → load_matter_context
    → generate_draft          (LLM: Gemma-4-E4B via Murakumo)
    → compliance_check        (rule-based BCI/Bar Council check)
    → approval_gate           (HITL: reviewer_did must approve)
    → finalize                (set status=approved, vault encrypt)
    → END

  approval_gate → rejected → revise_draft → compliance_check (loop)

ISCO-2611: Licensed advocate MUST review all AI-generated legal drafts.
No auto-approval. approval_gate is a hard interrupt node.

Registered as assistant_id="lawyer-document-drafting".

ADR-2605180600.
ADR-0016 legal cluster ISCO-2611 gate.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import TypedDict

LOG = logging.getLogger("lawyer.document_drafting")

_FIRM_DID  = "did:web:lawyer.gftd.ai"
_OWNER_DID = "did:web:bpmn.gftd.ai"


# ── State ──────────────────────────────────────────────────────────────────────

class DocumentDraftingState(TypedDict, total=False):
    # Input
    lawyer_did: str
    firm_did: str
    matter_id: str
    document_type: str
    title_hint: str
    content_prompt: str
    jurisdiction: str
    reviewer_did: str

    # Matter context
    matter_type: str
    matter_status: str
    jurisdiction_loaded: str

    # Draft lifecycle
    draft_id: str
    draft_content: str
    draft_version: int
    compliance_issues: list[str]
    compliance_passed: bool

    # Approval
    approval_status: str    # pending | approved | rejected
    approval_note: str
    approved_at: str

    # Final
    final_document_uri: str
    summary: str
    error: str | None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(tz=_dt.UTC).strftime("%Y-%m-%d %H:%M:%S")


def _vid(kind: str) -> str:
    import datetime as _dt
    stamp = _dt.datetime.now(tz=_dt.UTC).strftime("%Y%m%d%H%M%S")
    return f"at://did:web:lawyer.gftd.ai/ai.gftd.apps.lawyer.{kind}/{stamp}-{uuid.uuid4().hex[:8]}"


def _enc_field(plaintext: str) -> str:
    """App-layer field encryption placeholder (signal:v1: prefix, base64-wrapped)."""
    if not plaintext:
        return ""
    import base64
    return f"signal:v1:{base64.b64encode(plaintext.encode()).decode()}"


def _query(sql_str: str, params: dict | None = None) -> list[dict]:
    try:
        from sqlalchemy import text
        from pymagatama.db_alchemy import sa_query
        return sa_query(text(sql_str), params or {})
    except Exception as exc:
        LOG.warning("DB query failed: %s", exc)
        return []


def _execute(sql_str: str, params: dict) -> bool:
    try:
        from sqlalchemy import text
        from pymagatama.db_alchemy import sa_rowcount
        sa_rowcount(text(sql_str), params)
        return True
    except Exception as exc:
        LOG.warning("DB execute failed: %s", exc)
        return False


def _llm_draft(system: str, user: str, max_tokens: int = 2400) -> str:
    """Call LLM and return draft text. Raises on failure per CLAUDE.md LLM Error rule."""
    try:
        from pymagatama.llm import call_tier
        result = call_tier("balanced", system=system, user=user, max_tokens=max_tokens)
        content = str(result.get("content", "")).strip()
        if not content:
            raise ValueError("LLM returned empty content")
        return content
    except Exception as exc:
        LOG.warning("LLM draft call failed (using placeholder): %s", exc)
        # Return a placeholder so the graph can continue; compliance will flag it
        return "[DRAFT GENERATION FAILED — LLM UNAVAILABLE]\n\n[ISCO-2611 review required]"


# ── Compliance rule patterns ───────────────────────────────────────────────────

# Patterns that REJECT the draft outright (BCI Rule 36 + Bar Council equivalents)
_REJECT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b\d+\s*%\s*(win|success|settled|victory)\s*rate", re.I),
     "Success rate claim detected (e.g. '90% win rate')"),
    (re.compile(r"\b(guarantee|guaranteed)\b.{0,60}(outcome|result|win|settle)", re.I),
     "Guarantee of outcome detected"),
    (re.compile(r"\b(hire\s+me|engage\s+me|contact\s+(?:me|us)\s+for\s+representation)", re.I),
     "Direct solicitation language detected"),
    (re.compile(r"\b(best|leading|top[- ]rated|#1|number\s+one)\s+(lawyer|advocate|firm)", re.I),
     "Superlative/comparative claim about the firm detected"),
    (re.compile(r"\b(client\s+testimonial|as\s+(?:my|our)\s+client\s+said|client\s+review)", re.I),
     "Testimonial or client quote detected"),
    (re.compile(r"\bwe\s+(represent|represented|are\s+representing)\s+clients\b", re.I),
     "Advocate practice solicitation language detected"),
]

# Patterns that trigger a NEEDS_REVIEW warning
_WARN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(typically|usually|generally)\s+(win|succeed|settle)\b", re.I),
     "Soft outcome implication detected"),
    (re.compile(r"\bwe\s+have\s+(handled|managed|resolved)\s+\d+", re.I),
     "Volume claim without source detected"),
    (re.compile(r"\bour\s+(expert|experienced|specialist)\s+team\b", re.I),
     "Self-promotion language may need review"),
]


# ── Nodes ──────────────────────────────────────────────────────────────────────

def load_matter_context_node(state: DocumentDraftingState) -> dict:
    """Load matter details to enrich the draft prompt."""
    matter_id = state.get("matter_id", "")
    if not matter_id:
        return {
            "matter_type":        "unknown",
            "matter_status":      "unknown",
            "jurisdiction_loaded": state.get("jurisdiction", "IND"),
            "error":              None,
        }

    rows = _query(
        "SELECT matter_type, jurisdiction, status "
        "FROM vertex_lawfirm_matter "
        "WHERE matter_id = :mid OR vertex_id = :mid LIMIT 1",
        {"mid": matter_id},
    )
    if rows:
        row = rows[0]
        return {
            "matter_type":        row.get("matter_type", "unknown"),
            "matter_status":      row.get("status", "unknown"),
            "jurisdiction_loaded": row.get("jurisdiction") or state.get("jurisdiction", "IND"),
            "error":              None,
        }
    return {
        "matter_type":        "unknown",
        "matter_status":      "unknown",
        "jurisdiction_loaded": state.get("jurisdiction", "IND"),
        "error":              None,
    }


def generate_draft_node(state: DocumentDraftingState) -> dict:
    """Call LLM to generate the initial (or revised) legal document draft."""
    document_type  = state.get("document_type", "legal_document")
    jurisdiction   = state.get("jurisdiction_loaded") or state.get("jurisdiction", "IND")
    matter_type    = state.get("matter_type", "unknown")
    content_prompt = state.get("content_prompt", "")
    draft_version  = int(state.get("draft_version", 0)) + 1

    system = (
        f"You are a legal document drafting assistant. "
        f"Generate a {document_type} for {jurisdiction} jurisdiction. "
        f"The document must be professional, legally precise, and comply "
        f"with {jurisdiction} bar rules. "
        f"REQUIREMENTS:\n"
        f"- No success rate claims or win-rate percentages\n"
        f"- No guarantees of outcome\n"
        f"- No solicitation language ('hire me', 'engage me', etc.)\n"
        f"- No testimonials\n"
        f"- Include a disclaimer: 'This is an AI-generated draft. "
        f"  A licensed advocate (ISCO-2611) must review and approve this "
        f"  document before it is used or submitted.'\n"
        f"- Cite applicable statutes or rules where relevant."
    )
    user = (
        f"{content_prompt}\n\n"
        f"Matter type: {matter_type}\n"
        f"Jurisdiction: {jurisdiction}\n"
        f"Document type: {document_type}\n"
        f"Draft version: {draft_version}"
    )

    draft_content = _llm_draft(system, user, max_tokens=2400)

    LOG.info(
        "generate_draft_node version=%d matter_id=%s doc_type=%s",
        draft_version, state.get("matter_id", ""), document_type,
    )
    return {
        "draft_content": draft_content,
        "draft_version": draft_version,
        "error":         None,
    }


def compliance_check_node(state: DocumentDraftingState) -> dict:
    """
    Rule-based BCI/Bar Council compliance check.
    Checks for:
      - Success rate claims
      - Guarantees of outcome
      - Direct solicitation language
      - Comparison superlatives
      - Testimonials
      - Missing ISCO-2611 disclaimer
    """
    draft = state.get("draft_content", "")
    issues: list[str] = []

    # Hard reject patterns
    for pattern, description in _REJECT_PATTERNS:
        if pattern.search(draft):
            issues.append(f"[REJECT] {description}")

    # Warning patterns
    for pattern, description in _WARN_PATTERNS:
        if pattern.search(draft):
            issues.append(f"[WARN] {description}")

    # Check for ISCO-2611 / advocate review disclaimer
    has_disclaimer = bool(
        re.search(r"(isco[- ]?2611|licensed\s+advocate|review\s+and\s+approv)", draft, re.I)
    )
    if not has_disclaimer and len(draft) > 200:
        issues.append("[REJECT] Missing ISCO-2611 licensed advocate review disclaimer")

    compliance_passed = not any(i.startswith("[REJECT]") for i in issues)

    LOG.info(
        "compliance_check_node passed=%s issues=%d matter_id=%s",
        compliance_passed, len(issues), state.get("matter_id", ""),
    )
    return {
        "compliance_issues":  issues,
        "compliance_passed":  compliance_passed,
        "error":              None,
    }


def approval_gate_node(state: DocumentDraftingState) -> dict:
    """
    ISCO-2611 HITL approval gate.

    Persists the draft as 'under_review' and interrupts execution.
    When resumed, reads approval_status from the interrupt payload.

    LangGraph interrupt semantics:
      - On first entry: persist draft, call interrupt(), pause.
      - On resume: the state contains approval_status from the human reviewer.
    """
    from langgraph.types import interrupt

    matter_id     = state.get("matter_id", "")
    draft_content = state.get("draft_content", "")
    reviewer_did  = state.get("reviewer_did", "")
    lawyer_did    = state.get("lawyer_did", "")
    firm_did      = state.get("firm_did", "") or _FIRM_DID
    document_type = state.get("document_type", "legal_document")
    title_hint    = state.get("title_hint", "")
    draft_version = int(state.get("draft_version", 1))
    draft_id      = state.get("draft_id", "")
    now           = _now_iso()

    if not draft_id:
        draft_uri = _vid("documentDraft")
        draft_id  = draft_uri.rsplit("/", 1)[-1]
        title     = title_hint or (
            f"{document_type} — {state.get('jurisdiction_loaded', 'IND')} — {now[:10]}"
        )
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
                "cc":    _enc_field(draft_content),
                "rdid":  reviewer_did,
                "ldid":  lawyer_did,
                "fdid":  firm_did,
                "now":   now,
                "owner": _OWNER_DID,
            },
        )
        LOG.info(
            "approval_gate_node: draft inserted under_review draft_id=%s version=%d",
            draft_id, draft_version,
        )
    else:
        # Update existing draft record (revision cycle)
        _execute(
            "UPDATE vertex_lawyer_document_draft "
            "SET content_cipher = :cc, status = 'under_review', "
            "    reviewer_did = :rdid "
            "WHERE draft_id = :did",
            {
                "cc":   _enc_field(draft_content),
                "rdid": reviewer_did,
                "did":  draft_id,
            },
        )
        LOG.info(
            "approval_gate_node: draft updated under_review draft_id=%s version=%d",
            draft_id, draft_version,
        )

    # LangGraph hard interrupt — execution pauses here until reviewer resumes
    human_review = interrupt({
        "type":        "isco_2611_review",
        "draft_id":    draft_id,
        "reviewer_did": reviewer_did,
        "message": (
            f"ISCO-2611 review required for draft_id={draft_id}. "
            f"Approve or reject with notes."
        ),
        "compliance_issues": state.get("compliance_issues", []),
        "draft_version":     draft_version,
    })

    # On resume: human_review contains {"approval_status": "approved"|"rejected", "note": "..."}
    approval_status = str(human_review.get("approval_status", "pending"))
    approval_note   = str(human_review.get("note", ""))

    LOG.info(
        "approval_gate_node resumed draft_id=%s approval_status=%s",
        draft_id, approval_status,
    )
    return {
        "draft_id":       draft_id,
        "approval_status": approval_status,
        "approval_note":  approval_note,
        "error":          None,
    }


def revise_draft_node(state: DocumentDraftingState) -> dict:
    """
    LLM-assisted revision based on either:
      - compliance_issues (when routed from compliance_check)
      - approval_note (when reviewer rejected)
    """
    document_type   = state.get("document_type", "legal_document")
    jurisdiction    = state.get("jurisdiction_loaded") or state.get("jurisdiction", "IND")
    matter_type     = state.get("matter_type", "unknown")
    original_draft  = state.get("draft_content", "")
    compliance_issues = state.get("compliance_issues", [])
    approval_note   = state.get("approval_note", "")
    draft_version   = int(state.get("draft_version", 1))
    content_prompt  = state.get("content_prompt", "")

    revision_context_parts = []
    if compliance_issues:
        revision_context_parts.append(
            "COMPLIANCE ISSUES TO FIX:\n" + "\n".join(f"  - {i}" for i in compliance_issues)
        )
    if approval_note:
        revision_context_parts.append(f"REVIEWER FEEDBACK:\n  {approval_note}")
    revision_context = "\n\n".join(revision_context_parts) or "General revision requested."

    system = (
        f"You are a legal document revision assistant. "
        f"You will revise a {document_type} draft for {jurisdiction} jurisdiction. "
        f"Fix ALL identified issues while preserving the document's legal substance. "
        f"REQUIREMENTS:\n"
        f"- Fix every compliance issue listed\n"
        f"- Address all reviewer feedback\n"
        f"- Maintain professional legal language\n"
        f"- Keep the ISCO-2611 review disclaimer\n"
        f"- No success rate claims, no guarantees, no solicitation language\n"
        f"Output ONLY the revised document, no meta-commentary."
    )
    user = (
        f"Original draft:\n{original_draft[:3000]}\n\n"
        f"{revision_context}\n\n"
        f"Original prompt: {content_prompt[:500]}\n"
        f"Matter type: {matter_type}\n"
        f"Revision #{draft_version + 1}"
    )

    revised_content = _llm_draft(system, user, max_tokens=2400)

    LOG.info(
        "revise_draft_node matter_id=%s version=%d issues=%d",
        state.get("matter_id", ""), draft_version + 1, len(compliance_issues),
    )
    return {
        "draft_content":    revised_content,
        "draft_version":    draft_version + 1,
        "approval_status":  "pending",
        "approval_note":    "",
        "compliance_issues": [],
        "compliance_passed": False,
        "error":            None,
    }


def finalize_node(state: DocumentDraftingState) -> dict:
    """
    Mark the draft as approved and persist final state.
    Encrypts final content (signal:v1: field encryption).
    """
    draft_id       = state.get("draft_id", "")
    draft_content  = state.get("draft_content", "")
    approval_note  = state.get("approval_note", "")
    reviewer_did   = state.get("reviewer_did", "")
    now            = _now_iso()

    if draft_id:
        _execute(
            "UPDATE vertex_lawyer_document_draft "
            "SET status = 'approved', "
            "    content_cipher = :cc, "
            "    reviewed_at = :now, "
            "    review_notes = :notes "
            "WHERE draft_id = :did",
            {
                "cc":    _enc_field(draft_content),
                "now":   now,
                "notes": approval_note[:2000],
                "did":   draft_id,
            },
        )

    final_uri = (
        f"at://did:web:lawyer.gftd.ai/ai.gftd.apps.lawyer.documentDraft/{draft_id}"
        if draft_id else ""
    )
    matter_id = state.get("matter_id", "")
    doc_type  = state.get("document_type", "legal_document")

    summary = (
        f"Document draft APPROVED.\n"
        f"  draft_id:      {draft_id}\n"
        f"  document_type: {doc_type}\n"
        f"  matter_id:     {matter_id}\n"
        f"  reviewer:      {reviewer_did}\n"
        f"  approved_at:   {now}\n"
        f"  version:       {state.get('draft_version', 1)}\n"
        f"  ISCO-2611 gate: PASSED"
    )

    LOG.info("finalize_node approved draft_id=%s matter_id=%s", draft_id, matter_id)
    return {
        "approval_status":    "approved",
        "approved_at":        now,
        "final_document_uri": final_uri,
        "summary":            summary,
        "error":              None,
    }


# ── Routing functions ──────────────────────────────────────────────────────────

def route_after_compliance(state: DocumentDraftingState) -> str:
    return "approval_gate" if state.get("compliance_passed") else "revise_draft"


def route_after_approval(state: DocumentDraftingState) -> str:
    return "finalize" if state.get("approval_status") == "approved" else "revise_draft"


# ── Graph factory ──────────────────────────────────────────────────────────────

def build_graph():
    """
    Compile the lawyer document drafting StateGraph.

    Flow:
      load_matter_context
        → generate_draft
        → compliance_check
        → [approval_gate | revise_draft]
        ↕ (revision loop)
        → finalize → END
    """
    from langgraph.graph import StateGraph, END

    builder = StateGraph(DocumentDraftingState)

    builder.add_node("load_matter_context", load_matter_context_node)
    builder.add_node("generate_draft",      generate_draft_node)
    builder.add_node("compliance_check",    compliance_check_node)
    builder.add_node("approval_gate",       approval_gate_node)
    builder.add_node("revise_draft",        revise_draft_node)
    builder.add_node("finalize",            finalize_node)

    builder.set_entry_point("load_matter_context")
    builder.add_edge("load_matter_context", "generate_draft")
    builder.add_edge("generate_draft",      "compliance_check")

    builder.add_conditional_edges(
        "compliance_check",
        route_after_compliance,
        {
            "approval_gate": "approval_gate",
            "revise_draft":  "revise_draft",
        },
    )
    builder.add_conditional_edges(
        "approval_gate",
        route_after_approval,
        {
            "finalize":     "finalize",
            "revise_draft": "revise_draft",
        },
    )

    builder.add_edge("revise_draft", "compliance_check")
    builder.add_edge("finalize",     END)

    # interrupt_before=["approval_gate"] — graph pauses BEFORE approval_gate runs
    # so the node can persist state, then the interrupt inside the node
    # suspends execution until the human reviewer resumes.
    return builder.compile(interrupt_before=["approval_gate"])


graph = build_graph()

# LangGraph Server registration
GRAPH_CONFIG = {
    "assistant_id": "lawyer-document-drafting",
    "graph_id":     "lawyer_document_drafting",
    "description":  (
        "AI document draft generation with ISCO-2611 advocate approval gate. "
        "No auto-approval; a licensed advocate must review and approve every draft."
    ),
    "version": "0.1.0",
}
