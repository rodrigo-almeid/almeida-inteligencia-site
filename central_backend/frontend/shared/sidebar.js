/* Sidebar + breadcrumb compartilhados entre os módulos do central_backend.
 *
 * Cada página define window.SIDEBAR_CONFIG antes de carregar este script:
 *   window.SIDEBAR_CONFIG = {
 *     tag: 'Financeiro',                        // texto abaixo do logo
 *     ativo: 'contas',                           // id do item atual (bate com items[].id)
 *     items: [
 *       { id: 'dashboard', href: '/financeiro/dashboard.html', icon: 'dashboard', label: 'Dashboard' },
 *       ...
 *     ],
 *     breadcrumb: ['Portal', 'Financeiro', 'Contas'],  // opcional
 *   };
 *
 * Precisa de <div id="sidebar-root"></div> logo no início do <body> e,
 * opcionalmente, <div id="breadcrumb-root"></div> onde o caminho deve aparecer.
 */

const SIDEBAR_ICONS = {
  dashboard: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  contas: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
  combustivel: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M3 22V8l6-6h6l2 2v2h2a2 2 0 0 1 2 2v3"/><path d="M3 12h10"/><path d="M13 22V10"/><circle cx="18" cy="18" r="3"/><path d="M18 15v3l2 1"/></svg>',
  mercado: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>',
  credenciais: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
  agenda: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
  config: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
  console: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
  portal: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
};

const SIDEBAR_LOGO_SVG = `<svg viewBox="0 0 56 56" width="26" height="26">
  <polygon points="28,4 50,16 50,40 28,52 6,40 6,16" fill="none" stroke="#3DDB82" stroke-width="1.5"/>
  <circle cx="28" cy="20" r="3" fill="#3DDB82"/>
  <circle cx="18" cy="30" r="2.5" fill="#3DDB82" opacity=".7"/>
  <circle cx="38" cy="30" r="2.5" fill="#3DDB82" opacity=".7"/>
  <line x1="28" y1="23" x2="18" y2="28" stroke="#3DDB82" stroke-width=".8" opacity=".6"/>
  <line x1="28" y1="23" x2="38" y2="28" stroke="#3DDB82" stroke-width=".8" opacity=".6"/>
</svg>`;

function logout() {
  localStorage.removeItem('central_token');
  localStorage.removeItem('central_email');
  location.href = 'https://almeidainteligencia.com.br/';
}
window.logout = logout;

function toggleMobileSidebar() {
  document.querySelector('.sidebar').classList.toggle('mobile-open');
  document.querySelector('.sidebar-overlay').classList.toggle('active');
}
window.toggleMobileSidebar = toggleMobileSidebar;

function closeMobileSidebar() {
  document.querySelector('.sidebar').classList.remove('mobile-open');
  document.querySelector('.sidebar-overlay').classList.remove('active');
}
window.closeMobileSidebar = closeMobileSidebar;

function renderSidebar(config) {
  const root = document.getElementById('sidebar-root');
  if (!root) return;

  const items = config.items.map(item => `
    <a href="${item.href}" class="nav-item${item.id === config.ativo ? ' active' : ''}">
      ${SIDEBAR_ICONS[item.icon] || ''}
      ${item.label}
    </a>
  `).join('');

  root.innerHTML = `
    <button class="mobile-hamburger" onclick="toggleMobileSidebar()" aria-label="Menu">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
    </button>
    <div class="sidebar-overlay" onclick="closeMobileSidebar()"></div>

    <div class="sidebar">
      <div class="logo">
        ${SIDEBAR_LOGO_SVG}
        <div>
          <div class="name">Almeida <span>Inteligência</span></div>
          <div class="tag">${config.tag}</div>
        </div>
      </div>

      ${items}
      <a href="https://almeidainteligencia.com.br/dashboard/" class="nav-item" id="portal-link" style="display:none">
        ${SIDEBAR_ICONS.portal}
        Portal
      </a>

      <div class="sidebar-spacer"></div>
      <div class="user-chip">
        <div>Conta</div>
        <div class="email" id="user-email">—</div>
      </div>
      <button class="logout-btn" onclick="logout()">Sair</button>
    </div>
  `;

  const emailEl = document.getElementById('user-email');
  if (emailEl) emailEl.textContent = localStorage.getItem('central_email') || '—';

  try {
    const _at = localStorage.getItem('admin_token');
    if (_at) {
      const _p = JSON.parse(atob(_at.split('.')[1]));
      if (_p.perfil === 'admin' || (_p.sistemas || []).length > 1) {
        document.getElementById('portal-link').style.display = '';
      }
    }
  } catch (e) { /* token do portal ausente ou inválido — mantém o link oculto */ }

  if (config.breadcrumb) renderBreadcrumb(config.breadcrumb);
}

function renderBreadcrumb(partes) {
  const root = document.getElementById('breadcrumb-root');
  if (!root) return;
  root.innerHTML = `<div class="breadcrumb">${partes
    .map((p, i) => i === partes.length - 1
      ? `<span class="breadcrumb-atual">${p}</span>`
      : `<span>${p}</span><span class="breadcrumb-sep">/</span>`)
    .join('')}</div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  if (window.SIDEBAR_CONFIG) renderSidebar(window.SIDEBAR_CONFIG);
});
