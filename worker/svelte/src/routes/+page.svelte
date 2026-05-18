<script lang="ts">
  import { onMount } from 'svelte';

  const FIRM_DID = 'did:web:lawyer.gftd.ai';
  const LAWYER_DID = 'did:web:k-bakshi.gftd.ai';

  type Dashboard = {
    activeMatters: number;
    pendingGrants: number;
    upcomingHearings: number;
    unbilledHours: number;
    recentMatters: Array<{ matterId: string; matterType: string; jurisdiction: string; status: string; role: string }>;
    pendingGrantList: Array<{ grantDid: string; matterType: string; jurisdiction: string; role: string; expiresAt: string }>;
    hearingList: Array<{ hearingId: string; matterId: string; scheduledAt: string; courtName: string; hearingType: string }>;
  };

  let dashboard: Dashboard | null = null;
  let loading = true;
  let error = '';

  async function xrpc(nsid: string, params: Record<string, string> = {}) {
    const url = new URL(`/xrpc/${nsid}`, window.location.origin);
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    const resp = await fetch(url.toString());
    if (!resp.ok) throw new Error(`XRPC ${nsid} failed: ${resp.status}`);
    return resp.json();
  }

  onMount(async () => {
    try {
      dashboard = await xrpc('ai.gftd.apps.lawyer.getDashboard', {
        lawyerDid: LAWYER_DID,
        firmDid: FIRM_DID,
      });
    } catch (e) {
      error = String(e);
      // Fallback demo data
      dashboard = {
        activeMatters: 3,
        pendingGrants: 2,
        upcomingHearings: 1,
        unbilledHours: 240,
        recentMatters: [
          { matterId: 'matter-001', matterType: 'ni138', jurisdiction: 'IN-MH', status: 'active', role: 'coCounsel' },
          { matterId: 'matter-002', matterType: 'civil', jurisdiction: 'IN-DL', status: 'filed', role: 'lead' },
        ],
        pendingGrantList: [
          { grantDid: 'grant-001', matterType: 'ni138', jurisdiction: 'IN-MH', role: 'coCounsel', expiresAt: '2026-08-18' },
        ],
        hearingList: [
          { hearingId: 'hearing-001', matterId: 'matter-002', scheduledAt: '2026-06-01T10:00:00Z', courtName: 'Delhi High Court', hearingType: 'interim' },
        ],
      };
    } finally {
      loading = false;
    }
  });

  function formatDate(iso: string) {
    try { return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }); }
    catch { return iso; }
  }

  function statusColor(status: string) {
    return ({ active: '#3fb950', filed: '#58a6ff', hearing: '#f0883e', pending_pwc: '#d29922', closed: '#6e7681' } as Record<string, string>)[status] ?? '#6e7681';
  }
</script>

<svelte:head><title>Dashboard — Gftd Lawyer</title></svelte:head>

<div class="page">
  <header class="page-header">
    <h1>Dashboard</h1>
    <p class="sub">Attorney workspace · {LAWYER_DID}</p>
  </header>

  {#if loading}
    <div class="loading">Loading dashboard…</div>
  {:else if dashboard}
    <div class="stat-grid">
      <div class="stat-card">
        <p class="stat-label">Active Matters</p>
        <p class="stat-value">{dashboard.activeMatters}</p>
      </div>
      <div class="stat-card accent-yellow">
        <p class="stat-label">Pending Grants</p>
        <p class="stat-value">{dashboard.pendingGrants}</p>
        {#if dashboard.pendingGrants > 0}
          <a href="/grants" class="stat-action">Review →</a>
        {/if}
      </div>
      <div class="stat-card accent-blue">
        <p class="stat-label">Upcoming Hearings</p>
        <p class="stat-value">{dashboard.upcomingHearings}</p>
      </div>
      <div class="stat-card">
        <p class="stat-label">Unbilled Time</p>
        <p class="stat-value">{Math.floor(dashboard.unbilledHours / 60)}h {dashboard.unbilledHours % 60}m</p>
      </div>
    </div>

    <div class="panel-grid">
      <section class="panel">
        <h2>Recent Matters</h2>
        {#if dashboard.recentMatters.length}
          <ul class="item-list">
            {#each dashboard.recentMatters as m}
              <li>
                <a href="/matters/{m.matterId}" class="item-link">
                  <div class="item-main">
                    <span class="item-type">{m.matterType}</span>
                    <span class="item-id">{m.matterId}</span>
                  </div>
                  <div class="item-meta">
                    <span class="badge" style="color: {statusColor(m.status)}">{m.status}</span>
                    <span class="role-badge">{m.role}</span>
                    <span class="jurisdiction">{m.jurisdiction}</span>
                  </div>
                </a>
              </li>
            {/each}
          </ul>
          <a href="/matters" class="view-all">View all matters →</a>
        {:else}
          <p class="empty">No active matters</p>
        {/if}
      </section>

      <section class="panel">
        <h2>Pending Grant Invitations</h2>
        {#if dashboard.pendingGrantList.length}
          <ul class="item-list">
            {#each dashboard.pendingGrantList as g}
              <li>
                <div class="item-main">
                  <span class="item-type">{g.matterType}</span>
                  <span class="role-badge">{g.role}</span>
                </div>
                <div class="item-meta">
                  <span class="jurisdiction">{g.jurisdiction}</span>
                  <span class="expires">Expires {formatDate(g.expiresAt)}</span>
                </div>
              </li>
            {/each}
          </ul>
          <a href="/grants" class="view-all">Review grants →</a>
        {:else}
          <p class="empty">No pending grants</p>
        {/if}
      </section>

      <section class="panel last-panel">
        <h2>Upcoming Hearings</h2>
        {#if dashboard.hearingList.length}
          <ul class="item-list">
            {#each dashboard.hearingList as h}
              <li>
                <div class="item-main">
                  <span class="item-type">{h.hearingType}</span>
                  <span class="item-id">{h.courtName}</span>
                </div>
                <div class="item-meta">
                  <span class="date">{formatDate(h.scheduledAt)}</span>
                </div>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="empty">No upcoming hearings</p>
        {/if}
      </section>
    </div>
  {/if}
</div>

<style>
  .page { padding: 24px; max-width: 1100px; }
  .page-header { margin-bottom: 24px; }
  h1 { font-size: 24px; font-weight: 700; }
  .sub { color: #6e7681; font-size: 12px; font-family: monospace; margin-top: 4px; }
  .loading { color: #6e7681; padding: 40px; text-align: center; }

  .stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
  .stat-card {
    background: #161b22; border: 1px solid #21262d; border-radius: 8px;
    padding: 16px; position: relative;
  }
  .stat-card.accent-yellow { border-color: #d2992260; }
  .stat-card.accent-blue { border-color: #58a6ff40; }
  .stat-label { font-size: 12px; color: #6e7681; margin-bottom: 4px; }
  .stat-value { font-size: 28px; font-weight: 700; }
  .stat-action { display: inline-block; font-size: 12px; color: #58a6ff; text-decoration: none; margin-top: 6px; }

  .panel-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .panel { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 16px; }
  .last-panel { grid-column: 1 / -1; }
  h2 { font-size: 13px; font-weight: 600; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }

  .item-list { list-style: none; display: grid; gap: 8px; padding: 0; margin: 0; }
  .item-link { text-decoration: none; color: inherit; }
  .item-main { display: flex; align-items: center; gap: 8px; }
  .item-type { font-weight: 600; font-size: 13px; color: #e6edf3; font-family: monospace; }
  .item-id { font-size: 11px; color: #6e7681; font-family: monospace; }
  .item-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
  .badge { font-size: 11px; font-weight: 600; }
  .role-badge { font-size: 11px; background: #1f2937; border: 1px solid #30363d; border-radius: 4px; padding: 1px 6px; color: #8b949e; }
  .jurisdiction { font-size: 11px; color: #6e7681; font-family: monospace; }
  .expires { font-size: 11px; color: #d29922; }
  .date { font-size: 12px; color: #58a6ff; }
  .view-all { display: inline-block; margin-top: 12px; font-size: 12px; color: #58a6ff; text-decoration: none; }
  .empty { color: #6e7681; font-size: 13px; padding: 12px 0; }

  @media (max-width: 900px) {
    .stat-grid { grid-template-columns: repeat(2, 1fr); }
    .panel-grid { grid-template-columns: 1fr; }
    .last-panel { grid-column: auto; }
  }
</style>
