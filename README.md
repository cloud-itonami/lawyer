# lawyer.gftd.ai

Attorney-facing portal — matter workspace, grant acceptance, AI document drafting, time logging.

## Structure

| Directory | Contents |
|---|---|
| `worker/` | Cloudflare Worker (TypeScript + Svelte CSR) |
| `worker/src/app.ts` | XRPC command handlers |
| `worker/svelte/` | Svelte views (Dashboard, Matters, Grants, Drafts) |
| `python/primitives/` | Python task handlers (pyzeebe) |
| `python/langgraph/` | LangGraph graphs (LangServer) |
| `lexicons/lawyer/` | AT Protocol Lexicon JSON (NSID contract SSoT) |

## Development

### Worker
```bash
cd worker
pnpm install
cd svelte && pnpm install && pnpm build && cd ..
npx wrangler dev
```

### LangGraph (local)
```bash
cd python
pip install -e ".[dev]"
langgraph test --graph lawyer_matter_workspace
```

## XRPC Surface (`ai.gftd.apps.lawyer.*`)

| NSID | Type | Description |
|---|---|---|
| `getDashboard` | query | Dashboard: matters + grants + hearings |
| `listAssignedMatters` | query | Matters where lawyer is lead/coCounsel |
| `listPendingGrants` | query | externalCounselGrant invitations |
| `acceptGrant` | procedure | Accept grant → open workspace |
| `logWorkNote` | procedure | Encrypted work note + time entry |
| `submitDocumentDraft` | procedure | AI draft + ISCO-2611 review gate |

## ISCO-2611 Compliance

AI-generated legal documents require approval by a licensed advocate before use.
`submitDocumentDraft` triggers a LangGraph thread with `interrupt_before=["approval_gate"]`.
Reviewer DID must call the approval endpoint to resume the thread.

## LangGraph Graphs

| Graph ID | File | Description |
|---|---|---|
| `lawyer-matter-workspace` | `python/langgraph/lawyer_matter_workspace.py` | Supervisor + specialist agents |
| `lawyer-document-drafting` | `python/langgraph/lawyer_document_drafting.py` | AI draft + HITL approval |

## Related

- [lawfirm.gftd.ai](https://github.com/gftdcojp/lawfirm) — client-facing portal
- ADR-2605180600: Attorney Portal Design
