<script lang="ts">
  import { onMount } from 'svelte';

  const FIRM_DID = 'did:web:lawyer.gftd.ai';
  const LAWYER_DID = 'did:web:k-bakshi.gftd.ai';

  type Matter = {
    matterId: string;
    matterNumber: string;
    matterType: string;
    jurisdiction: string;
    status: string;
    role: string;
    openedAt: string;
    clientName?: string;
    counterpartyName?: string;
  };

  let matters: Matter[] = [];
  let loading = true;
  let error = '';
  let filterStatus = 'all';
  let filterRole = 'all';

  const STATUS_OPTIONS = ['all', 'active', 'filed', 'hearing', 'pending_pwc', 'closed'];
  const ROLE_OPTIONS = ['all', 'lead', 'coCounsel'];

  const DEMO_MATTERS: Matter[] = [
    {
      matterId: 'matter-001',
      matterNumber: 'GFT-2026-001',
      matterType: 'ni138',
      jurisdiction: 'IN-MH',
      status: 'active',
      role: 'coCounsel',
      openedAt: '2026-03-01T00:00:00Z',
      clientName: 'Gftd Japan K.K.',
      counterpartyName: 'Kagoshima University',
    },
    {
      matterId: 'matter-002',
      matterNumber: 'GFT-2026-002',
      matterType: 'civil',
      jurisdiction: 'IN-DL',
      status: 'filed',
      role: 'lead',
      openedAt: '2026-04-15T00:00:00Z',
      clientName: 'Gftd Japan K.K.',
    },
    {
      matterId: 'matter-003',
      matterNumber: 'GFT-2026-003',
      matterType: 'arbitration',
      jurisdiction: 'IN-MH',
      status: 'hearing',
      role: 'lead',
      openedAt: '2026-01-10T00:00:00Z',
      clientName: 'Etzhayyim LLC',
    },
  ];

  async function loadMatters() {
    loading = true;
    error = '';
    try {
      const url = new URL('/xrpc/ai.gftd.apps.lawyer.listAssignedMatters', window.location.origin);
      url.searchParams.set('lawyerDid', LAWYER_DID);
      url.searchParams.set('firmDid', FIRM_DID);
      if (filterStatus !== 'all') url.searchParams.set('status', filterStatus);
      if (filterRole !== 'all') url.searchParams.set('role', filterRole);
      const resp = await fetch(url.toString());
      if (!resp.ok) throw new Error(`listAssignedMatters failed: ${resp.status}`);
      const data = await resp.json();
      matters = data.matters ?? data;
    } catch (e) {
      error = String(e);
      // Apply filters to demo data
      matters = DEMO_MATTERS.filter((m) => {
        if (filterStatus !== 'all' && m.status !== filterStatus) return false;
        if (filterRole !== 'all' && m.role !== filterRole) return false;
        return true;
      });
    } finally {
      loading = false;
    }
  }

  onMount(() => { loadMatters(); });

  function handleFilterChange() { loadMatters(); }

  function formatDate(iso: string) {
    try { return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }); }
    catch { return iso; }
  }

  function statusColor(status: string) {
    return ({ active: '#3fb950', filed: '#58a6ff', hearing: '#f0883e', pending_pwc: '#d29922', closed: '#6e7681' } as Record<string, string>)[status] ?? '#6e7681';
  }

  function statusLabel(status: string) {
    return ({ active: 'Active', filed: 'Filed', hearing: 'Hearing', pending_pwc: 'PWC Pending', closed: 'Closed' } as Record<string, string>)[status] ?? status;
  }

  function navigateToMatter(id: string) {
    window.location.href = `/matters/${id}`;
  }
</script>

<svelte:head><title>Matters — Gftd Lawyer</title></svelte:head>

<div class="page">
  <header class="page-header">
    <h1>Assigned Matters</h1>
    <p class="sub">{LAWYER_DID}</p>
  </header>

  <div class="filter-bar">
    <div class="filter-group">
      <label for="status-filter">Status</label>
      <select id="status-filter" bind:value={filterStatus} on:change={handleFilterChange}>
        {#each STATUS_OPTIONS as opt}
          <option value={opt}>{opt === 'all' ? 'All statuses' : statusLabel(opt)}</option>
        {/each}
      </select>
    </div>
    <div class="filter-group">
      <label for="role-filter">Role</label>
      <select id="role-filter" bind:value={filterRole} on:change={handleFilterChange}>
        {#each ROLE_OPTIONS as opt}
          <option value={opt}>{opt === 'all' ? 'All roles' : opt}</option>
        {/each}
      </select>
    </div>
    <span class="count">{matters.length} matter{matters.length !== 1 ? 's' : ''}</span>
  </div>

  {#if loading}
    <div class="loading">Loading matters…</div>
  {:else if matters.length === 0}
    <div class="empty-state">
      <p>No matters match the current filters.</p>
    </div>
  {:else}
    <div class="matters-table">
      <div class="table-header">
        <span>Type / Number</span>
        <span>Jurisdiction</span>
        <span>Status</span>
        <span>Role</span>
        <span>Opened</span>
        <span>Actions</span>
      </div>
      {#each matters as matter}
        <div
          class="table-row"
          role="button"
          tabindex="0"
          on:click={() => navigateToMatter(matter.matterId)}
          on:keydown={(e) => e.key === 'Enter' && navigateToMatter(matter.matterId)}
        >
          <div class="cell cell-type">
            <span class="matter-type">{matter.matterType}</span>
            <span class="matter-number">{matter.matterNumber}</span>
            {#if matter.clientName}
              <span class="client-name">{matter.clientName}</span>
            {/if}
          </div>
          <div class="cell">
            <span class="jurisdiction">{matter.jurisdiction}</span>
          </div>
          <div class="cell">
            <span class="status-badge" style="color: {statusColor(matter.status)}; border-color: {statusColor(matter.status)}40;">
              {statusLabel(matter.status)}
            </span>
          </div>
          <div class="cell">
            <span class="role-badge">{matter.role}</span>
          </div>
          <div class="cell">
            <span class="date">{formatDate(matter.openedAt)}</span>
          </div>
          <div class="cell cell-actions" on:click|stopPropagation on:keydown|stopPropagation role="presentation">
            <a href="/matters/{matter.matterId}" class="btn-link">Open →</a>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { padding: 24px; max-width: 1100px; }
  .page-header { margin-bottom: 20px; }
  h1 { font-size: 24px; font-weight: 700; }
  .sub { color: #6e7681; font-size: 12px; font-family: monospace; margin-top: 4px; }

  .filter-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 16px;
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 12px 16px;
  }
  .filter-group { display: flex; align-items: center; gap: 8px; }
  .filter-group label { font-size: 12px; color: #6e7681; white-space: nowrap; }
  select {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-size: 13px;
    padding: 5px 10px;
    cursor: pointer;
  }
  select:focus { outline: none; border-color: #58a6ff; }
  .count { margin-left: auto; font-size: 12px; color: #6e7681; }

  .loading { color: #6e7681; padding: 40px; text-align: center; }
  .empty-state { text-align: center; padding: 48px 24px; color: #6e7681; background: #161b22; border: 1px solid #21262d; border-radius: 8px; }

  .matters-table { background: #161b22; border: 1px solid #21262d; border-radius: 8px; overflow: hidden; }

  .table-header {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr;
    gap: 12px;
    padding: 10px 16px;
    background: #1c2128;
    border-bottom: 1px solid #21262d;
    font-size: 11px;
    font-weight: 600;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .table-row {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid #21262d;
    cursor: pointer;
    transition: background 0.1s;
    align-items: center;
  }
  .table-row:last-child { border-bottom: none; }
  .table-row:hover { background: #1c2128; }

  .cell { display: flex; flex-direction: column; gap: 2px; }
  .matter-type { font-weight: 600; font-size: 13px; font-family: monospace; color: #e6edf3; }
  .matter-number { font-size: 11px; color: #6e7681; font-family: monospace; }
  .client-name { font-size: 11px; color: #8b949e; margin-top: 2px; }
  .jurisdiction { font-size: 12px; font-family: monospace; color: #8b949e; }
  .status-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 600;
    border: 1px solid;
    border-radius: 4px;
    padding: 2px 8px;
    width: fit-content;
  }
  .role-badge { font-size: 11px; background: #1f2937; border: 1px solid #30363d; border-radius: 4px; padding: 2px 8px; color: #8b949e; width: fit-content; }
  .date { font-size: 12px; color: #8b949e; }
  .cell-actions { flex-direction: row; align-items: center; }
  .btn-link { font-size: 12px; color: #58a6ff; text-decoration: none; white-space: nowrap; }
  .btn-link:hover { text-decoration: underline; }

  @media (max-width: 900px) {
    .table-header { display: none; }
    .table-row { grid-template-columns: 1fr 1fr; gap: 8px; }
    .cell-type { grid-column: 1 / -1; }
    .cell-actions { justify-content: flex-end; }
  }
</style>
