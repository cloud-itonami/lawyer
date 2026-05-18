<script lang="ts">
  import { page } from '$app/stores';

  const FIRM_DID = 'did:web:lawyer.gftd.ai';
  const LAWYER_DID = 'did:web:k-bakshi.gftd.ai'; // default, will be from auth

  const nav = [
    { href: '/', label: 'Dashboard', icon: '⚖️' },
    { href: '/matters', label: 'Matters', icon: '📁' },
    { href: '/grants', label: 'Grants', icon: '🤝' },
    { href: '/drafts', label: 'Drafts', icon: '📝' },
  ];
</script>

<div class="shell">
  <nav class="sidebar">
    <div class="logo">
      <span class="icon">⚖️</span>
      <div>
        <p class="name">Gftd Lawyer</p>
        <p class="did">{FIRM_DID}</p>
      </div>
    </div>

    <ul class="nav-list">
      {#each nav as item}
        <li class:active={$page.url.pathname === item.href || ($page.url.pathname.startsWith(item.href) && item.href !== '/')}>
          <a href={item.href}>
            <span class="nav-icon">{item.icon}</span>
            {item.label}
          </a>
        </li>
      {/each}
    </ul>

    <div class="sidebar-footer">
      <p class="label">Lead Bengoshi</p>
      <p class="value">k.bakshi</p>
      <p class="did-small">{LAWYER_DID}</p>
    </div>
  </nav>

  <main class="content">
    <slot />
  </main>
</div>

<style>
  :global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) {
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }

  .shell {
    display: flex;
    min-height: 100vh;
  }

  .sidebar {
    width: 240px;
    background: #161b22;
    border-right: 1px solid #21262d;
    display: flex;
    flex-direction: column;
    padding: 20px 0;
    flex-shrink: 0;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 20px 20px;
    border-bottom: 1px solid #21262d;
    margin-bottom: 16px;
  }

  .logo .icon { font-size: 28px; }
  .logo .name { font-weight: 700; font-size: 15px; color: #e6edf3; }
  .logo .did { font-size: 10px; color: #6e7681; font-family: monospace; overflow-wrap: anywhere; }

  .nav-list { list-style: none; flex: 1; }

  .nav-list li a {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 20px;
    color: #8b949e;
    text-decoration: none;
    border-radius: 0;
    transition: background 0.1s, color 0.1s;
  }

  .nav-list li a:hover { background: #1c2128; color: #e6edf3; }
  .nav-list li.active a { background: #1f2937; color: #58a6ff; border-left: 3px solid #58a6ff; }
  .nav-icon { font-size: 16px; width: 20px; }

  .sidebar-footer {
    padding: 16px 20px;
    border-top: 1px solid #21262d;
  }
  .sidebar-footer .label { font-size: 10px; color: #6e7681; text-transform: uppercase; letter-spacing: 0.5px; }
  .sidebar-footer .value { font-weight: 600; color: #e6edf3; margin-top: 2px; }
  .sidebar-footer .did-small { font-size: 10px; color: #6e7681; font-family: monospace; overflow-wrap: anywhere; }

  .content { flex: 1; overflow: auto; }

  @media (max-width: 768px) {
    .shell { flex-direction: column; }
    .sidebar { width: 100%; flex-direction: row; flex-wrap: wrap; padding: 12px; }
    .logo { border-bottom: none; padding-bottom: 0; margin-bottom: 0; }
    .nav-list { display: flex; gap: 4px; }
    .sidebar-footer { display: none; }
  }
</style>
