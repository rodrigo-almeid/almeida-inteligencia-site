/* Sidebar + breadcrumb compartilhados entre as páginas do Classificador de E-mails.
 *
 * Diferente do sidebar.js do central_backend: esse módulo é um serviço à parte
 * (email-backend), com seu próprio login e chave de sessão ('email_token' /
 * 'email_nome' no localStorage, não 'central_token'). Por isso este componente
 * só desenha a estrutura (logo, nav, esqueleto do user-chip, botão Sair) — quem
 * preenche o e-mail do usuário e decide se o link "Portal" aparece continua
 * sendo o próprio checarAuth() de cada página (fetch em /email/auth/me), do
 * jeito que já funcionava. Isso evita duplicar essa checagem sem necessidade.
 *
 * Cada página define window.SIDEBAR_CONFIG antes de carregar este script:
 *   window.SIDEBAR_CONFIG = {
 *     tag: 'Processos · IA · Resultados',
 *     moduleLabel: 'Classificador de E-mails',
 *     ativo: 'caixa',                 // id do item atual (bate com items[].id)
 *     items: [
 *       { id: 'caixa', type: 'link', href: '/email/dashboard.html', icon: 'caixa', label: 'Caixa de E-mails' },
 *       { id: 'config', type: 'link', href: '/email/contas.html', icon: 'config', label: 'Configuração de E-mails' },
 *       { id: 'nav-treinar', type: 'action', icon: 'treinar', label: 'Treinar IA' },       // vira <button id="nav-treinar">
 *       { id: 'nav-exportar', type: 'action', icon: 'exportar', label: 'Exportar Dataset' },
 *     ],
 *     breadcrumb: [
 *       { label: 'Portal', href: 'https://almeidainteligencia.com.br/dashboard/' },
 *       { label: 'Classificador de E-mails', href: '/email/dashboard.html' },
 *       { label: 'Caixa de E-mails' },
 *     ],
 *   };
 *
 * Precisa de <div id="sidebar-root"></div> logo no início do <body> e,
 * opcionalmente, <div id="breadcrumb-root"></div> dentro de <main> (ou o topo
 * da página), onde o caminho deve aparecer.
 */

const EMAIL_SIDEBAR_ICONS = {
  caixa: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>',
  config: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
  treinar: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
  exportar: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  portal: '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
};

const EMAIL_SIDEBAR_LOGO_SVG = `<svg viewBox="0 0 56 56" width="32" height="32">
  <polygon points="28,4 50,16 50,40 28,52 6,40 6,16" fill="none" stroke="#3DDB82" stroke-width="1.5"/>
  <circle cx="28" cy="20" r="3" fill="#3DDB82"/>
  <circle cx="18" cy="30" r="2.5" fill="#3DDB82" opacity="0.7"/>
  <circle cx="38" cy="30" r="2.5" fill="#3DDB82" opacity="0.7"/>
  <line x1="28" y1="23" x2="18" y2="28" stroke="#3DDB82" stroke-width="0.8" opacity="0.6"/>
  <line x1="28" y1="23" x2="38" y2="28" stroke="#3DDB82" stroke-width="0.8" opacity="0.6"/>
</svg>`;

function toggleMobileSidebar() {
  document.querySelector('aside').classList.toggle('mobile-open');
  document.querySelector('.sidebar-overlay').classList.toggle('active');
}
window.toggleMobileSidebar = toggleMobileSidebar;

function closeMobileSidebar() {
  document.querySelector('aside').classList.remove('mobile-open');
  document.querySelector('.sidebar-overlay').classList.remove('active');
}
window.closeMobileSidebar = closeMobileSidebar;

function renderSidebar(config) {
  const root = document.getElementById('sidebar-root');
  if (!root) return;

  const items = config.items.map(item => {
    const icon = EMAIL_SIDEBAR_ICONS[item.icon] || '';
    const activeClass = item.id === config.ativo ? ' active' : '';
    if (item.type === 'action') {
      return `<button id="${item.id}">${icon}${item.label}</button>`;
    }
    return `<a href="${item.href}" id="${item.id}" class="${activeClass.trim()}">${icon}${item.label}</a>`;
  }).join('');

  root.innerHTML = `
    <button class="mobile-hamburger" onclick="toggleMobileSidebar()" aria-label="Menu">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
    </button>
    <div class="sidebar-overlay" onclick="closeMobileSidebar()"></div>

    <aside>
      <div class="sidebar-brand">
        ${EMAIL_SIDEBAR_LOGO_SVG}
        <div class="brand-text">
          <div class="name">Almeida <span>Inteligência</span></div>
          <div class="tag">${config.tag || ''}</div>
        </div>
      </div>
      ${config.moduleLabel ? `<div class="sidebar-module">${config.moduleLabel}</div>` : ''}
      <nav>${items}</nav>
      <div class="sidebar-spacer"></div>
      <a href="https://almeidainteligencia.com.br/dashboard/" class="nav-item" id="portal-link" style="display:none">
        ${EMAIL_SIDEBAR_ICONS.portal}Portal
      </a>
      <div class="user-chip">
        <div class="user-chip-label">Conta</div>
        <div class="user-chip-email" id="sidebar-usuario-email">—</div>
      </div>
      <button class="btn-logout" id="btn-logout">Sair</button>
    </aside>
  `;

  if (config.breadcrumb) renderBreadcrumb(config.breadcrumb);
}

function renderBreadcrumb(partes) {
  const root = document.getElementById('breadcrumb-root');
  if (!root) return;
  root.innerHTML = `<div class="breadcrumb">${partes
    .map((p, i) => {
      const isUltimo = i === partes.length - 1;
      const item = isUltimo
        ? `<span class="breadcrumb-atual">${p.label}</span>`
        : `<a href="${p.href}" class="breadcrumb-link">${p.label}</a>`;
      return isUltimo ? item : `${item}<span class="breadcrumb-sep">/</span>`;
    })
    .join('')}</div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  if (window.SIDEBAR_CONFIG) renderSidebar(window.SIDEBAR_CONFIG);
});
