# Operator quickstart — attorney portal

Every command below was executed verbatim on 2026-08-19 and the observed output is
recorded next to it. Steps that **do not work** are recorded as such rather than
omitted — see [What is documented but does not run](#what-is-documented-but-does-not-run).

Measured on: macOS (darwin 25.3.0), node v26.3.0, pnpm 10.26.2, Python 3.14.5.
Version-sensitive results are marked. No lockfiles are committed (see
[Known gaps](#known-gaps)), so dependency resolution is re-done on every install
and the exact package versions below will drift. This is not hypothetical: two
runs twenty minutes apart on the same machine resolved svelte 5.55.3 and then
5.56.9, from an unchanged `package.json`.

---

## 1. What this repo actually deploys

Read this before the build steps — the layout is not what the top-level README's
structure table implies.

| | |
|---|---|
| Wrangler entrypoint | `worker/wrangler.jsonc` → `main: "svelte/.svelte-kit/cloudflare/_worker.js"` |
| That file is produced by | `worker/svelte` (SvelteKit + `@sveltejs/adapter-cloudflare`) |
| The live XRPC handler is | `worker/svelte/src/routes/xrpc/[...path]/+server.ts` |
| `worker/src/app.ts` is | **not deployed** — see below |

`worker/src/app.ts` is referenced only by the `"main"` field of
`worker/package.json`. Wrangler takes its entrypoint from `wrangler.jsonc`, and
that file names the SvelteKit output instead, so nothing imports `app.ts`.
Verified against a real build:

```bash
cd worker/svelte && pnpm install && pnpm build
# strings unique to src/app.ts — expect 0 for each
for s in "edge-langserver" "lawyer: endpoint not found" "DISPATCHER_URL" "sharedCommands"; do
  echo "$s -> $(grep -rl -F -- "$s" .svelte-kit/ | wc -l)"
done
# CONTROL — strings unique to the live route. If these are also 0 the probe is
# broken and proves nothing; they must be non-zero.
for s in "x-gftd-bff" "tools/call" "MCP router request failed"; do
  echo "$s -> $(grep -rl -F -- "$s" .svelte-kit/ | wc -l)"
done
```

Observed: all four `app.ts` strings `-> 0`; all three control strings `-> 1`.

The two handlers are not equivalent, so this is not a harmless duplicate:

| | `worker/src/app.ts` (dead) | `svelte/…/xrpc/[...path]/+server.ts` (live) |
|---|---|---|
| Upstream | `DISPATCHER_URL` + `DISPATCHER_INTERNAL_SECRET` | `AGENTGATEWAY_MCP_ROUTER_URL`, as MCP `tools/call` |
| NSID filter | only `ai.gftd.apps.lawyer.*` / `ai.gftd.apps.lawfirm.*` | none — proxies any path |
| `/health`, `/_worker/health`, `/_app/meta` | implemented | **absent** |
| Methods | GET + POST | POST + OPTIONS |

So the health endpoints and the NSID allow-list described in `app.ts` are not
running in production, and the deployed proxy is broader than the one documented.

---

## 2. Build and check the worker (works)

```bash
cd worker
pnpm install          # → devDependencies: + typescript 6.0.3 ; exit 0
npx tsc --noEmit      # → no output, exit 0
```

`typecheck` is the only script `worker/package.json` defines. It type-checks
`src/**/*.ts` — i.e. it checks the file that is **not** deployed. It does not
check the SvelteKit app; that is step 3.

```bash
cd worker/svelte
pnpm install          # → svelte + 6 devDeps ; exit 0
pnpm build            # → vite build; "Using @sveltejs/adapter-cloudflare ✔ done" ; exit 0
pnpm check            # → COMPLETED 147 FILES 0 ERRORS 0 WARNINGS 0 FILES_WITH_PROBLEMS ; exit 0
```

`pnpm install` prints a warning that build scripts for `esbuild` and `workerd`
were ignored. That is pnpm's default policy and the build above still succeeds;
`pnpm approve-builds` is not required for `pnpm build` or `pnpm check`.

After `pnpm build`, the two paths `wrangler.jsonc` points at exist:

```bash
ls .svelte-kit/cloudflare/_worker.js      # → the entrypoint
ls .svelte-kit/cloudflare/client          # → _app/  _headers   (the ASSETS binding)
```

**There is no `build/` directory.** `adapter-cloudflare` emits to
`.svelte-kit/cloudflare/`. This matters for the CI workflow — see
[Known gaps](#known-gaps).

### Running it locally

`npx wrangler dev` is the intended local run. It could not be verified on the
measuring workstation: the dev server reached `Ready on http://127.0.0.1:5299`
and then no connection was accepted, with the log full of
`Error: EMFILE: too many open files, watch`. `ulimit -n` was already 1048576, so
this is file-watcher exhaustion from the many concurrent processes on that
machine, **not** a defect in this repo. Treat `wrangler dev` as unverified here
and re-check it on a quiet machine. The static probe in §1 does not depend on a
running server.

---

## 3. Load the LangGraph graphs (works, but not the documented way)

The graphs are plain files under `python/langgraph/`. There is no installable
package and no `langgraph.json`, so neither `pip install -e .` nor the
`langgraph` CLI can see them. Load them by path instead:

```bash
python3 -m venv /tmp/lawyer-venv
/tmp/lawyer-venv/bin/pip install langgraph        # → langgraph 1.2.11
cd python
/tmp/lawyer-venv/bin/python -c "
import importlib.util as u
for path in ('langgraph/lawyer_matter_workspace.py', 'langgraph/lawyer_document_drafting.py'):
    s = u.spec_from_file_location('m', path); m = u.module_from_spec(s); s.loader.exec_module(m)
    print(path, '->', sorted(n for n in m.graph.get_graph().nodes if not n.startswith('__')))
"
```

Observed:

```
langgraph/lawyer_matter_workspace.py  -> ['aggregate', 'drafting', 'grants', 'hearings', 'matters', 'supervisor', 'time_entry']
langgraph/lawyer_document_drafting.py -> ['approval_gate', 'compliance_check', 'finalize', 'generate_draft', 'load_matter_context', 'revise_draft']
```

Both modules call `build_graph()` at import time, so a successful import is also
a successful `StateGraph` compile.

Note that `python/README.md` states the drafting flow as
`load_matter_context → generate_draft → compliance_check → approval_gate → finalize`
and omits `revise_draft`, which the node list above shows is real: both
`compliance_check` and `approval_gate` can route into it, and it loops back to
`compliance_check`.

### The ISCO-2611 approval gate

The README's claim that the graph pauses before `approval_gate` is true and is
checkable:

```bash
cd python
/tmp/lawyer-venv/bin/python -c "
import importlib.util as u
s = u.spec_from_file_location('m', 'langgraph/lawyer_document_drafting.py')
m = u.module_from_spec(s); s.loader.exec_module(m)
print('interrupt_before =', m.graph.interrupt_before_nodes)
"
```

Observed: `interrupt_before = ['approval_gate']`.

Importing does **not** call an LLM or a database; the node bodies do, at run time.
Nothing above executes a graph, so no credentials are needed for any step in this
document.

---

## What is documented but does not run

Verified failures of commands published in the READMEs, as of this commit.

### `cd python && pip install -e ".[dev]"` — fails

There is no `pyproject.toml` and no `setup.py` anywhere in the repo. Reproduced
in a clean virtualenv, so this is not the host's PEP-668 policy:

```
ERROR: file:///…/python does not appear to be a Python project:
neither 'setup.py' nor 'pyproject.toml' found.
```

### `langgraph test --graph lawyer_matter_workspace` — no such command

`langgraph-cli` 0.4.31 answers `Error: No such command 'test'.` It offers
`build`, `deploy`, `dev`, `dockerfile`, `new`, `up`, `validate`. There is no `test` subcommand and no `--graph` flag. There is
also no `langgraph.json`, which `langgraph dev` and `langgraph validate` both
require. Use the by-path loader in §3.

---

## Known gaps

Recorded so the next operator does not rediscover them. None are fixed by this
document.

1. **`worker/src/app.ts` is dead code** (§1). It is the file the top-level README
   describes as "XRPC command handlers", and the `/health` endpoint and NSID
   allow-list it implements are not deployed. Deleting it or wiring it in is a
   product decision, not a docs one.
2. **`.github/workflows/deploy.yml` cannot run, and would not work if it could.**
   GitHub Actions is disabled on this repository — `gh api
   repos/cloud-itonami/lawyer/actions/permissions` returns `{"enabled": false}` —
   under the fleet-wide policy that CI/CD runs on the murakumo fleet
   (ADR-2607300900). Independently of that, the workflow has three faults that
   have therefore never been exercised:
   - `cache-dependency-path: worker/svelte/pnpm-lock.yaml` — that file does not exist;
   - `pnpm install --frozen-lockfile` in both `worker/` and `worker/svelte/` — verified
     against a pristine clone, this exits 1 with `ERR_PNPM_NO_LOCKFILE`;
   - it uploads and re-downloads `worker/svelte/build/`, which `adapter-cloudflare`
     never produces (the output is `.svelte-kit/cloudflare/`), so the deploy step
     would ship whatever happened to be on disk rather than the built artifact.
3. **No lockfiles are committed.** `worker/pnpm-lock.yaml` and
   `worker/svelte/pnpm-lock.yaml` are both absent, so installs re-resolve every
   time and the package versions in §2 are not reproducible.
4. **No tests.** The repo has no test files in any language. `pnpm check` and
   `tsc --noEmit` are type checks: they do not execute the XRPC route or any
   graph node. Nothing here would catch a behavioural regression.
5. **`worker/package.json` `"main": "src/app.ts"`** points at the dead file and is
   the only thing that still suggests it is an entrypoint.
