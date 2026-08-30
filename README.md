# Attorney-facing portal

Attorney-facing portal — matter workspace, grant acceptance, AI document drafting, time logging.

**Operators start at [`docs/operator-quickstart.md`](docs/operator-quickstart.md)**, which
records the exact commands that were run, their observed output, and the ones that fail.

## Structure

| Directory | Contents |
|---|---|
| `worker/` | Cloudflare Worker (SvelteKit edge BFF) |
| `worker/wrangler.jsonc` | Deployment config — its `main` is the **SvelteKit** build output |
| `worker/svelte/` | Svelte views (Dashboard, Matters, Grants, Drafts) **and the live XRPC route** |
| `worker/svelte/src/routes/xrpc/[...path]/+server.ts` | The XRPC handler that is actually deployed |
| `worker/src/app.ts` | An XRPC handler that is **not deployed** — see below |
| `python/primitives/` | Python task handlers (pyzeebe) |
| `python/langgraph/` | LangGraph graphs (LangServer) |
| `lexicons/lawyer/` | AT Protocol Lexicon JSON (NSID contract SSoT) |

## Development

```bash
cd worker        && pnpm install && npx tsc --noEmit      # typecheck src/app.ts
cd worker/svelte && pnpm install && pnpm build && pnpm check
```

Both blocks exit 0 on node 26 / pnpm 10. `pnpm build` writes
`.svelte-kit/cloudflare/`, which is what `wrangler.jsonc` deploys; there is no
`build/` directory. `npx wrangler dev` is the intended local run but was not
verifiable on the measuring workstation — the quickstart records why.

The LangGraph graphs load by file path once `langgraph` is installed in a
virtualenv; the quickstart has the exact loader and the verified node lists. No
credentials are needed to compile them.

## Declared but not implemented

Verified against this commit. Listed here rather than quietly corrected, because
choosing between dropping the declaration and building the thing is a product
decision, not a documentation one.

| Declared where | Declaration | Actual |
|---|---|---|
| README (before this commit) | `cd python && pip install -e ".[dev]"` | No `pyproject.toml` or `setup.py` exists — fails in a clean virtualenv |
| README (before this commit) | `langgraph test --graph lawyer_matter_workspace` | `langgraph-cli` has no `test` subcommand and no `--graph` flag; there is also no `langgraph.json` |
| `worker/src/app.ts` | `/health`, `/_worker/health`, `/_app/meta` | Not in the deployed bundle. The live route implements none of them |
| `worker/src/app.ts` | NSID allow-list (`ai.gftd.apps.lawyer.*` / `.lawfirm.*`) | The live route proxies **any** path to the MCP router |
| `worker/package.json` | `"main": "src/app.ts"` | Wrangler reads `wrangler.jsonc`, whose `main` is the SvelteKit output |
| `python/README.md` | drafting flow ends `… → approval_gate → finalize` | The compiled graph also has `revise_draft`, reachable from both `compliance_check` and `approval_gate` |
| `.github/workflows/deploy.yml` | push-to-main deploy | Actions is disabled on this repo (fleet CI runs on murakumo, ADR-2607300900). The workflow also references a lockfile and a `build/` directory that do not exist |

## XRPC Surface (`ai.gftd.apps.lawyer.*`)

Declared by the lexicons in `lexicons/lawyer/`. The deployed route forwards each
NSID to the MCP router as a `tools/call`; it does not implement them itself.

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
The drafting graph is compiled with `interrupt_before=["approval_gate"]`, so it
pauses before that node runs and a reviewer DID must resume the thread. This one
is verified — the quickstart shows how to read `interrupt_before` off the
compiled graph.

## LangGraph Graphs

| Graph ID | File | Description |
|---|---|---|
| `lawyer-matter-workspace` | `python/langgraph/lawyer_matter_workspace.py` | Supervisor + specialist agents |
| `lawyer-document-drafting` | `python/langgraph/lawyer_document_drafting.py` | AI draft + HITL approval |

## Tests

There are none, in any language. `pnpm check` and `tsc --noEmit` are type checks
and do not execute the XRPC route or any graph node, so nothing in this repo
would catch a behavioural regression.

## Related

- [lawfirm](https://github.com/cloud-itonami/lawfirm) — client-facing portal
- ADR-2605180600: Attorney Portal Design
