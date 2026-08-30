# Python — attorney portal

## Task Handlers (pyzeebe)

| Task | Handler | Description |
|---|---|---|
| `lawyer.dashboard.get` | `task_lawyer_dashboard_get` | Dashboard snapshot |
| `lawyer.matters.list` | `task_lawyer_matters_list` | Assigned matters |
| `lawyer.grants.list` | `task_lawyer_grants_list` | Pending grants |
| `lawyer.grant.accept` | `task_lawyer_grant_accept` | Accept grant |
| `lawyer.work_note.log` | `task_lawyer_work_note_log` | Work note + time |
| `lawyer.document_draft.submit` | `task_lawyer_document_draft_submit` | AI draft |

## LangGraph Graphs

### `lawyer-matter-workspace`
Supervisor pattern: routes to matters/grants/hearings/drafting specialists.

### `lawyer-document-drafting`
Sequential with HITL gate:
```
load_matter_context → generate_draft → compliance_check → approval_gate → finalize
```
`approval_gate` is a hard interrupt (ISCO-2611 — licensed advocate must approve).
