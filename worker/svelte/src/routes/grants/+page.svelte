<script lang="ts">
  import { onMount } from 'svelte';

  const FIRM_DID = 'did:web:lawyer.gftd.ai';
  const LAWYER_DID = 'did:web:k-bakshi.gftd.ai';

  type Grant = {
    grantDid: string;
    matterDid?: string;
    matterType: string;
    jurisdiction: string;
    role: string;
    capabilities: string[];
    expiresAt: string;
    grantingFirmDid: string;
    grantingFirmName?: string;
    status: 'invited' | 'accepted' | 'declined' | 'expired';
    acceptedAt?: string;
    acceptanceNote?: string;
  };

  let pendingGrants: Grant[] = [];
  let acceptedGrants: Grant[] = [];
  let loading = true;
  let acceptingGrantDid = '';
  let acceptNotes: Record<string, string> = {};
  let successMsg = '';
  let errorMsg = '';

  const DEMO_PENDING: Grant[] = [
    {
      grantDid: 'grant-001',
      matterType: 'ni138',
      jurisdiction: 'IN-MH',
      role: 'coCounsel',
      capabilities: ['read', 'comment', 'uploadDocument'],
      expiresAt: '2026-08-18T00:00:00Z',
      grantingFirmDid: 'did:web:lawfirm.gftd.ai',
      grantingFirmName: 'Gftd Lawfirm',
      status: 'invited',
    },
    {
      grantDid: 'grant-002',
      matterType: 'arbitration',
      jurisdiction: 'SG',
      role: 'lead',
      capabilities: ['read', 'comment', 'uploadDocument', 'propose', 'scheduleHearing'],
      expiresAt: '2026-09-01T00:00:00Z',
      grantingFirmDid: 'did:web:singapore-law.example',
      grantingFirmName: 'Singapore Arbitration Partners',
      status: 'invited',
    },
  ];

  const DEMO_ACCEPTED: Grant[] = [
    {
      grantDid: 'grant-000',
      matterType: 'civil',
      jurisdiction: 'IN-DL',
      role: 'coCounsel',
      capabilities: ['read', 'comment'],
      expiresAt: '2027-01-01T00:00:00Z',
      grantingFirmDid: 'did:web:lawfirm.gftd.ai',
      grantingFirmName: 'Gftd Lawfirm',
      status: 'accepted',
      acceptedAt: '2026-04-01T09:30:00Z',
    },
  ];

  onMount(async () => {
    try {
      const url = new URL('/xrpc/ai.gftd.apps.lawyer.listPendingGrants', window.location.origin);
      url.searchParams.set('lawyerDid', LAWYER_DID);
      const resp = await fetch(url.toString());
      if (!resp.ok) throw new Error(`listPendingGrants failed: ${resp.status}`);
      const data = await resp.json();
      pendingGrants = (data.grants ?? data).filter((g: Grant) => g.status === 'invited');
      acceptedGrants = (data.grants ?? data).filter((g: Grant) => g.status === 'accepted');
    } catch {
      pendingGrants = DEMO_PENDING;
      acceptedGrants = DEMO_ACCEPTED;
    } finally {
      loading = false;
    }
  });

  async function acceptGrant(grantDid: string) {
    acceptingGrantDid = grantDid;
    successMsg = '';
    errorMsg = '';
    try {
      const resp = await fetch('/xrpc/ai.gftd.apps.lawyer.acceptGrant', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          grantDid,
          lawyerDid: LAWYER_DID,
          firmDid: FIRM_DID,
          acceptanceNote: acceptNotes[grantDid] ?? '',
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as { error?: string }).error ?? `acceptGrant failed: ${resp.status}`);
      }
      const grant = pendingGrants.find((g) => g.grantDid === grantDid);
      if (grant) {
        const now = new Date().toISOString();
        acceptedGrants = [{ ...grant, status: 'accepted', acceptedAt: now, acceptanceNote: acceptNotes[grantDid] }, ...acceptedGrants];
      }
      pendingGrants = pendingGrants.filter((g) => g.grantDid !== grantDid);
      successMsg = `Grant ${grantDid} accepted. Matter workspace is now open.`;
    } catch (e) {
      errorMsg = String(e);
    } finally {
      acceptingGrantDid = '';
    }
  }

  function formatDate(iso: string) {
    try { return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }); }
    catch { return iso; }
  }

  function capabilityLabel(cap: string) {
    return ({ read: 'Read', comment: 'Comment', uploadDocument: 'Upload Docs', propose: 'Propose', sign: 'Sign', scheduleHearing: 'Schedule Hearing' } as Record<string, string>)[cap] ?? cap;
  }
</script>

<svelte:head><title>Grants — Gftd Lawyer</title></svelte:head>

<div class="page">
  <header class="page-header">
    <h1>Grant Invitations</h1>
    <p class="sub">Co-counsel and matter access grants · {LAWYER_DID}</p>
  </header>

  {#if successMsg}
    <div class="alert alert-success">{successMsg}</div>
  {/if}
  {#if errorMsg}
    <div class="alert alert-error">{errorMsg}</div>
  {/if}

  {#if loading}
    <div class="loading">Loading grants…</div>
  {:else}
    <section class="section">
      <h2>Pending Invitations ({pendingGrants.length})</h2>
      {#if pendingGrants.length === 0}
        <div class="empty-state">No pending grant invitations.</div>
      {:else}
        <div class="grants-list">
          {#each pendingGrants as grant}
            <div class="grant-card pending">
              <div class="grant-header">
                <div class="grant-meta">
                  <span class="matter-type">{grant.matterType}</span>
                  <span class="jurisdiction">{grant.jurisdiction}</span>
                  <span class="role-badge">{grant.role}</span>
                </div>
                <div class="expires-badge">Expires {formatDate(grant.expiresAt)}</div>
              </div>

              <div class="grant-body">
                <div class="firm-info">
                  <span class="firm-label">Granting firm</span>
                  <span class="firm-name">{grant.grantingFirmName ?? grant.grantingFirmDid}</span>
                  <span class="firm-did">{grant.grantingFirmDid}</span>
                </div>

                <div class="capabilities">
                  <span class="cap-label">Capabilities granted</span>
                  <div class="cap-chips">
                    {#each grant.capabilities as cap}
                      <span class="cap-chip">{capabilityLabel(cap)}</span>
                    {/each}
                  </div>
                </div>

                <div class="grant-did-row">
                  <span class="grant-did-label">Grant DID</span>
                  <span class="grant-did-val">{grant.grantDid}</span>
                </div>
              </div>

              <div class="grant-actions">
                <div class="note-input-wrap">
                  <label for="note-{grant.grantDid}">Acceptance note (optional)</label>
                  <input
                    id="note-{grant.grantDid}"
                    type="text"
                    placeholder="e.g. Happy to assist on this matter."
                    bind:value={acceptNotes[grant.grantDid]}
                  />
                </div>
                <button
                  class="btn-accept"
                  disabled={acceptingGrantDid === grant.grantDid}
                  on:click={() => acceptGrant(grant.grantDid)}
                >
                  {acceptingGrantDid === grant.grantDid ? 'Accepting…' : 'Accept Grant'}
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <section class="section">
      <h2>Accepted Grants ({acceptedGrants.length})</h2>
      {#if acceptedGrants.length === 0}
        <div class="empty-state">No accepted grants yet.</div>
      {:else}
        <div class="grants-list">
          {#each acceptedGrants as grant}
            <div class="grant-card accepted">
              <div class="grant-header">
                <div class="grant-meta">
                  <span class="matter-type">{grant.matterType}</span>
                  <span class="jurisdiction">{grant.jurisdiction}</span>
                  <span class="role-badge">{grant.role}</span>
                </div>
                <div class="accepted-badge">Accepted {grant.acceptedAt ? formatDate(grant.acceptedAt) : ''}</div>
              </div>
              <div class="grant-body">
                <div class="firm-info">
                  <span class="firm-label">From</span>
                  <span class="firm-name">{grant.grantingFirmName ?? grant.grantingFirmDid}</span>
                </div>
                <div class="capabilities">
                  <div class="cap-chips">
                    {#each grant.capabilities as cap}
                      <span class="cap-chip muted">{capabilityLabel(cap)}</span>
                    {/each}
                  </div>
                </div>
                {#if grant.acceptanceNote}
                  <p class="acceptance-note">"{grant.acceptanceNote}"</p>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>
  {/if}
</div>

<style>
  .page { padding: 24px; max-width: 900px; }
  .page-header { margin-bottom: 24px; }
  h1 { font-size: 24px; font-weight: 700; }
  .sub { color: #6e7681; font-size: 12px; font-family: monospace; margin-top: 4px; }
  .loading { color: #6e7681; padding: 40px; text-align: center; }

  .alert {
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
    margin-bottom: 16px;
  }
  .alert-success { background: #1a3a1f; border: 1px solid #3fb95040; color: #3fb950; }
  .alert-error { background: #3a1a1a; border: 1px solid #f8514940; color: #f85149; }

  .section { margin-bottom: 32px; }
  h2 { font-size: 13px; font-weight: 600; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }

  .empty-state { color: #6e7681; font-size: 13px; padding: 24px; background: #161b22; border: 1px solid #21262d; border-radius: 8px; text-align: center; }

  .grants-list { display: grid; gap: 12px; }

  .grant-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    overflow: hidden;
  }
  .grant-card.pending { border-color: #d2992240; }
  .grant-card.accepted { border-color: #3fb95030; opacity: 0.85; }

  .grant-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: #1c2128;
    border-bottom: 1px solid #21262d;
    flex-wrap: wrap;
    gap: 8px;
  }
  .grant-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .matter-type { font-weight: 700; font-size: 14px; font-family: monospace; color: #e6edf3; }
  .jurisdiction { font-size: 12px; font-family: monospace; color: #6e7681; background: #0d1117; border: 1px solid #30363d; border-radius: 4px; padding: 1px 6px; }
  .role-badge { font-size: 11px; background: #1f2937; border: 1px solid #30363d; border-radius: 4px; padding: 2px 8px; color: #8b949e; }
  .expires-badge { font-size: 12px; color: #d29922; }
  .accepted-badge { font-size: 12px; color: #3fb950; }

  .grant-body { padding: 16px; display: grid; gap: 12px; }
  .firm-info { display: flex; flex-direction: column; gap: 2px; }
  .firm-label { font-size: 10px; color: #6e7681; text-transform: uppercase; letter-spacing: 0.5px; }
  .firm-name { font-size: 13px; font-weight: 600; color: #e6edf3; }
  .firm-did { font-size: 10px; color: #6e7681; font-family: monospace; }

  .capabilities { display: flex; flex-direction: column; gap: 6px; }
  .cap-label { font-size: 10px; color: #6e7681; text-transform: uppercase; letter-spacing: 0.5px; }
  .cap-chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .cap-chip { font-size: 11px; background: #1f2937; border: 1px solid #30363d; border-radius: 4px; padding: 2px 8px; color: #58a6ff; }
  .cap-chip.muted { color: #6e7681; }

  .grant-did-row { display: flex; flex-direction: column; gap: 2px; }
  .grant-did-label { font-size: 10px; color: #6e7681; text-transform: uppercase; letter-spacing: 0.5px; }
  .grant-did-val { font-size: 11px; font-family: monospace; color: #6e7681; overflow-wrap: anywhere; }

  .acceptance-note { font-size: 12px; color: #8b949e; font-style: italic; }

  .grant-actions {
    padding: 12px 16px;
    background: #1c2128;
    border-top: 1px solid #21262d;
    display: flex;
    align-items: flex-end;
    gap: 12px;
    flex-wrap: wrap;
  }
  .note-input-wrap { flex: 1; display: flex; flex-direction: column; gap: 4px; min-width: 200px; }
  .note-input-wrap label { font-size: 11px; color: #6e7681; }
  input[type="text"] {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-size: 13px;
    padding: 7px 10px;
    width: 100%;
  }
  input[type="text"]:focus { outline: none; border-color: #58a6ff; }

  .btn-accept {
    background: #238636;
    border: 1px solid #2ea043;
    border-radius: 6px;
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 20px;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s;
  }
  .btn-accept:hover:not(:disabled) { background: #2ea043; }
  .btn-accept:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
