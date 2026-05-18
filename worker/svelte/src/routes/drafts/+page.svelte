<script lang="ts">
  import { onMount } from 'svelte';

  const FIRM_DID = 'did:web:lawyer.gftd.ai';
  const LAWYER_DID = 'did:web:k-bakshi.gftd.ai';

  const DOCUMENT_TYPES = [
    { value: 'vakalatnama', label: 'Vakalatnama' },
    { value: 'notice', label: 'Legal Notice' },
    { value: 'reply', label: 'Reply / Written Statement' },
    { value: 'petition', label: 'Petition' },
    { value: 'affidavit', label: 'Affidavit' },
    { value: 'brief', label: 'Brief / Argument Sheet' },
  ];

  type DraftStatus = 'under_review' | 'approved' | 'rejected';

  type Draft = {
    draftId: string;
    matterId: string;
    documentType: string;
    titleHint?: string;
    jurisdiction?: string;
    status: DraftStatus;
    generatedContent?: string;
    createdAt: string;
    approvedAt?: string;
    reviewerDid?: string;
    langserverRunId?: string;
  };

  // Form state
  let formDocumentType = 'vakalatnama';
  let formMatterId = '';
  let formJurisdiction = '';
  let formPrompt = '';
  let formTitleHint = '';
  let formReviewerDid = '';

  // UI state
  let submitting = false;
  let submitError = '';
  let submitResult: Draft | null = null;

  // Recent drafts
  let recentDrafts: Draft[] = [];
  let loadingDrafts = true;

  const DEMO_DRAFTS: Draft[] = [
    {
      draftId: 'draft-001',
      matterId: 'matter-001',
      documentType: 'vakalatnama',
      jurisdiction: 'IN-MH',
      status: 'approved',
      createdAt: '2026-05-10T08:00:00Z',
      approvedAt: '2026-05-10T14:30:00Z',
      reviewerDid: LAWYER_DID,
      langserverRunId: 'run-abc123',
    },
    {
      draftId: 'draft-002',
      matterId: 'matter-002',
      documentType: 'notice',
      jurisdiction: 'IN-DL',
      status: 'under_review',
      createdAt: '2026-05-17T11:00:00Z',
      reviewerDid: LAWYER_DID,
      langserverRunId: 'run-def456',
    },
  ];

  onMount(async () => {
    try {
      // No direct list endpoint for drafts in spec; use demo data
      recentDrafts = DEMO_DRAFTS;
    } catch {
      recentDrafts = DEMO_DRAFTS;
    } finally {
      loadingDrafts = false;
    }
  });

  async function handleSubmit(e: Event) {
    e.preventDefault();
    if (!formMatterId.trim() || !formPrompt.trim()) {
      submitError = 'Matter ID and content prompt are required.';
      return;
    }
    submitting = true;
    submitError = '';
    submitResult = null;
    try {
      const payload: Record<string, string> = {
        lawyerDid: LAWYER_DID,
        firmDid: FIRM_DID,
        matterId: formMatterId.trim(),
        documentType: formDocumentType,
        contentPrompt: formPrompt.trim(),
      };
      if (formTitleHint.trim()) payload.titleHint = formTitleHint.trim();
      if (formJurisdiction.trim()) payload.jurisdiction = formJurisdiction.trim();
      if (formReviewerDid.trim()) payload.reviewerDid = formReviewerDid.trim();

      const resp = await fetch('/xrpc/ai.gftd.apps.lawyer.submitDocumentDraft', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error((err as { error?: string }).error ?? `submitDocumentDraft failed: ${resp.status}`);
      }
      const data: Draft = await resp.json();
      submitResult = data;
      recentDrafts = [data, ...recentDrafts];
      // Reset form
      formMatterId = '';
      formPrompt = '';
      formTitleHint = '';
      formJurisdiction = '';
      formReviewerDid = '';
    } catch (e) {
      submitError = String(e);
      // Show demo result
      submitResult = {
        draftId: `draft-${Date.now()}`,
        matterId: formMatterId.trim() || 'matter-demo',
        documentType: formDocumentType,
        jurisdiction: formJurisdiction || undefined,
        status: 'under_review',
        createdAt: new Date().toISOString(),
        reviewerDid: formReviewerDid || LAWYER_DID,
        langserverRunId: `run-demo-${Date.now()}`,
        generatedContent: `[AI-generated ${formDocumentType} draft for matter ${formMatterId.trim() || 'matter-demo'}]\n\nNote: Backend not reachable. This is a placeholder draft awaiting ISCO-2611 review.\n\nPrompt used: ${formPrompt.trim()}`,
      };
    } finally {
      submitting = false;
    }
  }

  function statusColor(status: DraftStatus) {
    return { under_review: '#d29922', approved: '#3fb950', rejected: '#f85149' }[status] ?? '#6e7681';
  }

  function statusLabel(status: DraftStatus) {
    return { under_review: 'Under Review', approved: 'Approved', rejected: 'Rejected' }[status] ?? status;
  }

  function formatDate(iso: string) {
    try { return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
    catch { return iso; }
  }
</script>

<svelte:head><title>Drafts — Gftd Lawyer</title></svelte:head>

<div class="page">
  <header class="page-header">
    <h1>AI Document Drafting</h1>
    <p class="sub">Generate legal document drafts · ISCO-2611 review required before use</p>
  </header>

  <div class="isco-notice">
    <span class="isco-icon">⚠️</span>
    <div>
      <strong>ISCO-2611 Compliance Notice</strong>
      <p>All AI-generated legal drafts require review and approval by a licensed advocate (ISCO-2611) before use in any legal proceeding, filing, or client communication.</p>
    </div>
  </div>

  <div class="layout">
    <section class="form-panel">
      <h2>New Draft Request</h2>
      <form on:submit={handleSubmit}>
        <div class="field">
          <label for="doc-type">Document Type</label>
          <select id="doc-type" bind:value={formDocumentType}>
            {#each DOCUMENT_TYPES as dt}
              <option value={dt.value}>{dt.label}</option>
            {/each}
          </select>
        </div>

        <div class="field">
          <label for="matter-id">Matter ID <span class="required">*</span></label>
          <input id="matter-id" type="text" placeholder="matter-001" bind:value={formMatterId} required />
        </div>

        <div class="field">
          <label for="title-hint">Title Hint (optional)</label>
          <input id="title-hint" type="text" placeholder="e.g. Vakalatnama for Gftd Japan K.K." bind:value={formTitleHint} />
        </div>

        <div class="field">
          <label for="jurisdiction">Jurisdiction</label>
          <input id="jurisdiction" type="text" placeholder="e.g. IN-MH" bind:value={formJurisdiction} />
        </div>

        <div class="field">
          <label for="reviewer-did">Reviewer DID (optional — defaults to lead Bengoshi)</label>
          <input id="reviewer-did" type="text" placeholder="did:web:..." bind:value={formReviewerDid} />
        </div>

        <div class="field">
          <label for="prompt">Content Prompt <span class="required">*</span></label>
          <textarea
            id="prompt"
            rows="5"
            placeholder="Describe the matter, parties, and what this document should accomplish…"
            bind:value={formPrompt}
            required
          ></textarea>
        </div>

        {#if submitError}
          <div class="field-error">{submitError}</div>
        {/if}

        <button type="submit" class="btn-submit" disabled={submitting}>
          {submitting ? 'Generating draft…' : 'Submit for AI Drafting'}
        </button>
      </form>
    </section>

    {#if submitResult}
      <section class="result-panel">
        <div class="result-header">
          <h2>Draft Generated</h2>
          <span class="status-badge" style="color: {statusColor(submitResult.status)}; border-color: {statusColor(submitResult.status)}40;">
            {statusLabel(submitResult.status)}
          </span>
        </div>

        <div class="result-meta">
          <div class="meta-row">
            <span class="meta-label">Draft ID</span>
            <span class="meta-val">{submitResult.draftId}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">Document Type</span>
            <span class="meta-val">{submitResult.documentType}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">Matter</span>
            <span class="meta-val">{submitResult.matterId}</span>
          </div>
          {#if submitResult.reviewerDid}
            <div class="meta-row">
              <span class="meta-label">Reviewer</span>
              <span class="meta-val">{submitResult.reviewerDid}</span>
            </div>
          {/if}
          {#if submitResult.langserverRunId}
            <div class="meta-row">
              <span class="meta-label">LangServer Run</span>
              <span class="meta-val">{submitResult.langserverRunId}</span>
            </div>
          {/if}
        </div>

        {#if submitResult.status === 'under_review'}
          <div class="review-notice">
            <strong>Awaiting ISCO-2611 Review</strong>
            <p>The assigned reviewer will be notified. The draft content is encrypted (signal:v1:) and accessible only to authorized parties. You will be notified when the review is complete.</p>
          </div>
        {/if}

        {#if submitResult.generatedContent}
          <div class="draft-content">
            <div class="draft-content-header">
              <span>Draft Preview</span>
              <span class="encrypted-notice">Content encrypted (signal:v1:) in production</span>
            </div>
            <pre>{submitResult.generatedContent}</pre>
          </div>
        {/if}
      </section>
    {/if}
  </div>

  <section class="recent-section">
    <h2>Recent Drafts</h2>
    {#if loadingDrafts}
      <div class="loading">Loading drafts…</div>
    {:else if recentDrafts.length === 0}
      <div class="empty-state">No drafts yet.</div>
    {:else}
      <div class="drafts-list">
        {#each recentDrafts as draft}
          <div class="draft-row">
            <div class="draft-info">
              <span class="draft-type">{draft.documentType}</span>
              <span class="draft-matter">{draft.matterId}</span>
              {#if draft.jurisdiction}
                <span class="draft-juris">{draft.jurisdiction}</span>
              {/if}
            </div>
            <div class="draft-meta">
              <span class="draft-id">{draft.draftId}</span>
              <span class="draft-date">{formatDate(draft.createdAt)}</span>
            </div>
            <div class="draft-status">
              <span class="status-badge sm" style="color: {statusColor(draft.status)}; border-color: {statusColor(draft.status)}40;">
                {statusLabel(draft.status)}
              </span>
              {#if draft.status === 'approved' && draft.approvedAt}
                <span class="approved-at">Approved {formatDate(draft.approvedAt)}</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>
</div>

<style>
  .page { padding: 24px; max-width: 1100px; }
  .page-header { margin-bottom: 20px; }
  h1 { font-size: 24px; font-weight: 700; }
  .sub { color: #6e7681; font-size: 12px; margin-top: 4px; }

  .isco-notice {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    background: #1a1a0a;
    border: 1px solid #d2992260;
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 24px;
  }
  .isco-icon { font-size: 20px; flex-shrink: 0; margin-top: 1px; }
  .isco-notice strong { font-size: 13px; color: #d29922; display: block; margin-bottom: 4px; }
  .isco-notice p { font-size: 12px; color: #8b949e; margin: 0; }

  .layout { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 32px; align-items: start; }
  h2 { font-size: 13px; font-weight: 600; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 16px; }

  .form-panel {
    background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px;
  }

  form { display: grid; gap: 14px; }

  .field { display: flex; flex-direction: column; gap: 6px; }
  .field label { font-size: 12px; color: #8b949e; }
  .required { color: #f85149; }

  select, input[type="text"] {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-size: 13px;
    padding: 7px 10px;
    width: 100%;
  }
  select:focus, input[type="text"]:focus { outline: none; border-color: #58a6ff; }

  textarea {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-size: 13px;
    padding: 8px 10px;
    width: 100%;
    resize: vertical;
    font-family: inherit;
  }
  textarea:focus { outline: none; border-color: #58a6ff; }

  .field-error { font-size: 12px; color: #f85149; background: #3a1a1a; border: 1px solid #f8514940; border-radius: 6px; padding: 8px 12px; }

  .btn-submit {
    background: #1f6feb;
    border: 1px solid #388bfd;
    border-radius: 6px;
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    padding: 9px 20px;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-submit:hover:not(:disabled) { background: #388bfd; }
  .btn-submit:disabled { opacity: 0.5; cursor: not-allowed; }

  .result-panel {
    background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px;
    display: grid; gap: 16px;
  }
  .result-header { display: flex; align-items: center; justify-content: space-between; }

  .status-badge {
    font-size: 11px; font-weight: 600; border: 1px solid; border-radius: 4px; padding: 2px 8px;
    display: inline-block;
  }
  .status-badge.sm { font-size: 10px; }

  .result-meta { display: grid; gap: 6px; }
  .meta-row { display: flex; gap: 12px; align-items: baseline; }
  .meta-label { font-size: 11px; color: #6e7681; width: 100px; flex-shrink: 0; text-transform: uppercase; letter-spacing: 0.3px; }
  .meta-val { font-size: 12px; font-family: monospace; color: #8b949e; overflow-wrap: anywhere; }

  .review-notice {
    background: #1a1a0a;
    border: 1px solid #d2992230;
    border-radius: 6px;
    padding: 12px 14px;
  }
  .review-notice strong { font-size: 12px; color: #d29922; display: block; margin-bottom: 4px; }
  .review-notice p { font-size: 12px; color: #8b949e; margin: 0; }

  .draft-content { border: 1px solid #21262d; border-radius: 6px; overflow: hidden; }
  .draft-content-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 12px; background: #1c2128; border-bottom: 1px solid #21262d;
    font-size: 11px; color: #6e7681;
  }
  .encrypted-notice { font-size: 10px; color: #6e7681; font-style: italic; }
  pre {
    padding: 12px; margin: 0; font-size: 12px; font-family: monospace;
    white-space: pre-wrap; overflow-wrap: anywhere; color: #8b949e; background: #0d1117; max-height: 260px; overflow-y: auto;
  }

  .recent-section { margin-top: 8px; }
  .loading { color: #6e7681; padding: 20px; text-align: center; font-size: 13px; }
  .empty-state { color: #6e7681; font-size: 13px; padding: 24px; background: #161b22; border: 1px solid #21262d; border-radius: 8px; text-align: center; }

  .drafts-list { background: #161b22; border: 1px solid #21262d; border-radius: 8px; overflow: hidden; }
  .draft-row {
    display: grid;
    grid-template-columns: 2fr 2fr 1fr;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid #21262d;
    align-items: center;
  }
  .draft-row:last-child { border-bottom: none; }

  .draft-info { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .draft-type { font-weight: 600; font-size: 13px; font-family: monospace; color: #e6edf3; }
  .draft-matter { font-size: 11px; color: #6e7681; font-family: monospace; }
  .draft-juris { font-size: 11px; background: #1f2937; border: 1px solid #30363d; border-radius: 4px; padding: 1px 6px; color: #8b949e; }

  .draft-meta { display: flex; flex-direction: column; gap: 2px; }
  .draft-id { font-size: 11px; font-family: monospace; color: #6e7681; }
  .draft-date { font-size: 11px; color: #6e7681; }

  .draft-status { display: flex; flex-direction: column; gap: 4px; align-items: flex-end; }
  .approved-at { font-size: 10px; color: #3fb950; }

  @media (max-width: 900px) {
    .layout { grid-template-columns: 1fr; }
    .draft-row { grid-template-columns: 1fr 1fr; }
    .draft-meta { display: none; }
  }
</style>
