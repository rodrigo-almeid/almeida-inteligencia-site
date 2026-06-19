const API = '/email/api';
let paginaAtual = 1;
let totalPaginas = 1;
let emailDetalheId = null;
let todasSubcategorias = [];
let todasContas = [];

const SUBCATS_POR_CAT = {
  "VT": ["Compra de VT – Admissão","Compra de VT – Extra","Vínculo de carga ao cartão",
         "Gestão de saldo","2ª via de cartão VT","Comunicados da operadora VT","Emails gerenciais – VT"],
  "VR": ["Compra de VR","2ª via de cartão VR"],
  "Outros": ["Recebimento de boleto","Recebimento de NF","Não classificado"],
};

// ── Auth ───────────────────────────────────────────────────────────────────
function token() { return localStorage.getItem('email_token'); }
function headers(json = true) {
  const h = { 'Authorization': `Bearer ${token()}` };
  if (json) h['Content-Type'] = 'application/json';
  return h;
}
function fazerLogout() { localStorage.removeItem('email_token'); localStorage.removeItem('email_nome'); window.location.href = '/email/'; }

async function checarAuth() {
  const t = token();
  if (!t) { window.location.href = '/email/'; return; }
  try {
    const res = await fetch(`${API.replace('/api','/auth')}/me`, { headers: headers() });
    if (!res.ok) { fazerLogout(); return; }
    const u = await res.json();
    document.getElementById('sidebar-usuario-email').textContent = u.email || u.nome;
    try {
      const at = localStorage.getItem('admin_token');
      if (at) {
        const p = JSON.parse(atob(at.split('.')[1]));
        if (p.perfil === 'admin' || (p.sistemas || []).length > 1)
          document.getElementById('portal-link').style.display = '';
      }
    } catch (_) {}
  } catch (_) { fazerLogout(); }
}

// ── Toast ──────────────────────────────────────────────────────────────────
let _toastTimer = null;
function toast(msg, tipo = 'ok') {
  const el = document.getElementById('toast');
  const msgEl = document.getElementById('toast-msg');
  const icone = tipo === 'ok' ? '✓' : tipo === 'erro' ? '✕' : 'ℹ';
  const cor = tipo === 'ok' ? 'var(--green-primary)' : tipo === 'erro' ? '#E24B4A' : '#E6B432';
  msgEl.innerHTML = `<span style="color:${cor}">${icone}</span> ${msg}`;
  el.style.display = 'block';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.style.display = 'none', 4000);
}

// ── Badges ─────────────────────────────────────────────────────────────────
function badgeSla(v) {
  if (!v) return '<span style="color:var(--gray-moss);font-size:12px">—</span>';
  const map = { 'D+0':'background:rgba(226,75,74,0.15);color:#E24B4A', 'D+1':'background:rgba(230,140,50,0.15);color:#E68C32',
                'D+2':'background:rgba(230,180,50,0.12);color:#E6B432', 'D+3+':'background:rgba(255,255,255,0.06);color:var(--gray-light)' };
  return `<span class="tag-sla" style="${map[v]||''}">${v}</span>`;
}
function badgeCategoria(v) {
  if (!v) return '<span style="color:var(--gray-moss);font-size:12px">—</span>';
  return `<span class="tag-categoria">${v}</span>`;
}
function badgeStatus(v) {
  const label = { 'nao_classificado':'não classif.' };
  return `<span class="tag-status status-${v}">${label[v]||v}</span>`;
}
function iconeGerencial(v) {
  return v==='sim' ? '<span style="color:#E24B4A" title="Gerencial">⚠</span>' : '';
}
function fmtData(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
}
function truncar(txt, n=50) { return txt && txt.length>n ? txt.slice(0,n)+'…' : (txt||''); }

// ── Subcategorias ──────────────────────────────────────────────────────────
async function carregarSubcategorias() {
  try {
    const res = await fetch(`${API}/subcategorias`, { headers: headers() });
    if (res.ok) todasSubcategorias = await res.json();
  } catch (_) {}
  const sel = document.getElementById('filtro-subcategoria');
  todasSubcategorias.forEach(s => {
    const opt = document.createElement('option'); opt.value=s; opt.textContent=s; sel.appendChild(opt);
  });
}
function atualizarSubcategoriasModal() {
  const cat = document.getElementById('det-categoria').value;
  const sel = document.getElementById('det-subcategoria');
  const lista = cat ? (SUBCATS_POR_CAT[cat]||[]) : todasSubcategorias;
  sel.innerHTML = '<option value="">— Sem subcategoria —</option>';
  lista.forEach(s => { const o=document.createElement('option'); o.value=s; o.textContent=s; sel.appendChild(o); });
}

// ── Modal de progresso ─────────────────────────────────────────────────────
const ICONE_TIPO = {
  info:   { icon:'fa-circle-info',          cor:'text-blue-400'   },
  import: { icon:'fa-envelope-open',        cor:'text-indigo-400' },
  ia:     { icon:'fa-brain',                cor:'text-purple-400' },
  aviso:  { icon:'fa-triangle-exclamation', cor:'text-yellow-400' },
  ok:     { icon:'fa-circle-check',         cor:'text-green-400'  },
  erro:   { icon:'fa-circle-xmark',         cor:'text-red-400'    },
};

function abrirModalProgresso(titulo, icone, corBtn) {
  document.getElementById('progresso-log').innerHTML = '';
  document.getElementById('progresso-rodape').style.display = 'none';
  document.getElementById('progresso-titulo').textContent = titulo;
  document.getElementById('progresso-icone').textContent = icone === 'fa-brain' ? '◈' : '↓';
  document.getElementById('progresso-pill').textContent = 'em andamento…';
  document.getElementById('modal-progresso').classList.remove('hidden');
}
function fecharModalProgresso() { document.getElementById('modal-progresso').classList.add('hidden'); }

function _iniciarPolling(jobId, onConcluido) {
  const logEl = document.getElementById('progresso-log');
  const pill  = document.getElementById('progresso-pill');
  let visto = 0, tentativas = 0;

  const poll = setInterval(async () => {
    if (++tentativas > 240) {
      clearInterval(poll);
      pill.textContent = 'tempo esgotado';
      document.getElementById('progresso-rodape').style.display = 'block';
      return;
    }
    try {
      const res = await fetch(`${API}/job/${jobId}`, { headers: headers() });
      const job = await res.json();

      const novas = (job.progresso || []).slice(visto);
      novas.forEach(p => {
        const div = document.createElement('div');
        div.style.cssText = 'padding:3px 0;border-bottom:0.5px solid rgba(255,255,255,0.05)';
        div.textContent = p.msg;
        logEl.appendChild(div);
      });
      visto += novas.length;
      logEl.scrollTop = logEl.scrollHeight;

      if (job.status === 'concluido') {
        clearInterval(poll);
        pill.textContent = 'concluído';
        pill.classList.remove('animate-pulse');
        document.getElementById('progresso-rodape').style.display = 'block';
        onConcluido(job.resultado);
      } else if (job.status === 'erro') {
        clearInterval(poll);
        pill.textContent = 'erro';
        document.getElementById('progresso-rodape').style.display = 'block';
        toast('Erro: ' + (job.erro || 'desconhecido'), 'erro');
      }
    } catch (_) {}
  }, 1000);
}

// ── Extração ───────────────────────────────────────────────────────────────
async function executarExtracao() {
  const btn = document.getElementById('btn-extrair');
  btn.disabled = true;
  btn.innerHTML = '↻ Extraindo…';
  abrirModalProgresso('Extraindo E-mails', 'fa-download', 'text-indigo-400');

  try {
    const res = await fetch(`${API}/extrair`, { method: 'POST', headers: headers() });
    const data = await res.json();
    if (!res.ok) { fecharModalProgresso(); toast(data.detail || 'Erro na extração.', 'erro'); }
    else _iniciarPolling(data.job_id, (r) => {
      if (r) {
        let msg = `${r.extraidos} importado(s)`;
        if (r.ignorados_duplicados) msg += ` · ${r.ignorados_duplicados} duplicado(s)`;
        if (r.restantes) msg += ` · Restam ~${r.restantes} — extraia novamente`;
        toast(msg, r.restantes ? 'aviso' : 'ok');
      }
      carregarEmails(); verificarPendentes();
    });
  } catch (err) { fecharModalProgresso(); toast('Erro: ' + err.message, 'erro'); }
  finally { btn.disabled=false; btn.innerHTML='↓ Extrair E-mails'; }
}

// ── Classificação ──────────────────────────────────────────────────────────
async function executarClassificacao() {
  const btn = document.getElementById('btn-classificar');
  btn.disabled = true;
  btn.innerHTML = '↻ Classificando…';
  abrirModalProgresso('Classificando com IA', 'fa-brain', 'text-purple-400');

  try {
    const res = await fetch(`${API}/classificar`, { method: 'POST', headers: headers() });
    const data = await res.json();
    if (!res.ok) { fecharModalProgresso(); toast(data.detail || 'Erro.', 'erro'); }
    else _iniciarPolling(data.job_id, (r) => {
      if (r) toast(`${r.classificados} classificado(s)${r.nao_classificados ? ` · ${r.nao_classificados} sem classificação` : ''}`, 'ok');
      carregarEmails(); verificarPendentes();
    });
  } catch (err) { fecharModalProgresso(); toast('Erro: ' + err.message, 'erro'); }
  finally { btn.disabled=false; btn.innerHTML='◈ Classificar E-mails'; }
}

// ── Exportar Dataset ────────────────────────────────────────────────────────
function exportarDataset() {
  fetch(`${API}/exportar-dataset`, { headers: headers() })
    .then(r => r.ok ? r.blob() : Promise.reject())
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href=url; a.download='dataset_emails.json'; a.click();
      URL.revokeObjectURL(url); toast('Dataset exportado!', 'ok');
    })
    .catch(() => toast('Erro ao exportar.', 'erro'));
}

// ── Pendentes / Modelo ──────────────────────────────────────────────────────
async function verificarPendentes() {
  try {
    const res = await fetch(`${API}/pendentes`, { headers: headers() });
    if (!res.ok) return;
    const { pendentes } = await res.json();
    const badge = document.getElementById('badge-pendentes');
    if (pendentes > 0) { badge.textContent = `${pendentes} aguardando classificação`; badge.style.display = 'inline-block'; }
    else badge.style.display = 'none';
  } catch (_) {}
}

async function verificarModelo() {
  try {
    const res = await fetch(`${API}/modelo-status`, { headers: headers() });
    if (!res.ok) return;
    const s = await res.json();
    const badge = document.getElementById('badge-modelo');
    const btn = document.getElementById('btn-classificar');

    if (s.subcategoria || s.sla) {
      const partes = [s.subcategoria&&'Subcategoria', s.sla&&'SLA'].filter(Boolean);
      badge.textContent = `IA ativa: ${partes.join(' + ')}`;
      badge.className = 'badge badge-green';
      btn.disabled = false;
      btn.title = '';
    } else {
      badge.textContent = 'IA não treinada';
      badge.className = 'badge badge-gray';
      btn.disabled = true;
      btn.title = 'Treine o modelo antes de classificar';
    }
    badge.style.display = 'inline-block';
  } catch (_) {}
}

// ── Modal Treinar ───────────────────────────────────────────────────────────
function abrirModalTreinar() { document.getElementById('treinar-status').style.display='none'; document.getElementById('modal-treinar').classList.remove('hidden'); }
function fecharModalTreinar() { document.getElementById('modal-treinar').classList.add('hidden'); }
async function executarTreinamento() {
  const btn = document.getElementById('btn-confirmar-treinar');
  const statusEl = document.getElementById('treinar-status');
  btn.disabled=true; btn.innerHTML='↻ Treinando…';
  try {
    const res = await fetch(`${API}/treinar`, { method:'POST', headers: headers() });
    const data = await res.json();
    if (!res.ok) { toast(data.detail||'Erro.','erro'); return; }
    let html='';
    for (const [alvo, info] of Object.entries(data)) {
      if (info.status==='insuficiente')
        html+=`<div style="color:#E6B432;margin-bottom:6px">⚠ <b>${alvo}</b>: insuficiente (${info.amostras} amostras, mín. 5)</div>`;
      else {
        html+=`<div style="color:var(--green-primary);margin-bottom:4px">✓ <b>${alvo}</b>: ${(info.acuracia*100).toFixed(1)}% — ${info.amostras_treino} treino / ${info.amostras_teste} teste</div>`;
        html+=`<div style="font-size:11px;color:var(--gray-moss);margin-bottom:8px;padding-left:14px">Classes: ${info.classes.join(', ')}</div>`;
      }
    }
    statusEl.innerHTML=html; statusEl.style.display='block';
    toast('Treinamento concluído!','ok'); verificarModelo();
  } catch (err) { toast('Erro: '+err.message,'erro'); }
  finally { btn.disabled=false; btn.innerHTML='◈ Iniciar Treinamento'; }
}

// ── Contas (apenas filtro da tabela) ──────────────────────────────────────
async function carregarContas() {
  try {
    const res = await fetch(`${API}/contas`, { headers: headers() });
    if (!res.ok) return;
    todasContas = await res.json();
    const sel = document.getElementById('filtro-conta');
    sel.innerHTML = '<option value="">Todas as contas</option>';
    todasContas.forEach(c => {
      const o = document.createElement('option'); o.value = c.id; o.textContent = c.nome; sel.appendChild(o);
    });
  } catch (_) {}
}

// ── Filtros / Paginação ────────────────────────────────────────────────────
function getFiltros() {
  return {
    busca:        document.getElementById('campo-busca').value.trim(),
    conta_id:     document.getElementById('filtro-conta').value,
    categoria:    document.getElementById('filtro-categoria').value,
    subcategoria: document.getElementById('filtro-subcategoria').value,
    sla:          document.getElementById('filtro-sla').value,
    status:       document.getElementById('filtro-status').value,
  };
}
function aplicarFiltros() { paginaAtual=1; carregarEmails(); }
function limparFiltros() {
  ['campo-busca','filtro-conta','filtro-categoria','filtro-subcategoria','filtro-sla','filtro-status']
    .forEach(id => document.getElementById(id).value='');
  aplicarFiltros();
}
function mudarPagina(delta) {
  const nova = paginaAtual+delta;
  if (nova<1||nova>totalPaginas) return;
  paginaAtual=nova; carregarEmails();
}

// ── Tabela ─────────────────────────────────────────────────────────────────
async function carregarEmails() {
  const f = getFiltros();
  const params = new URLSearchParams({ page:paginaAtual, por_pagina:20 });
  if (f.busca)        params.set('busca',f.busca);
  if (f.conta_id)     params.set('conta_id',f.conta_id);
  if (f.categoria)    params.set('categoria',f.categoria);
  if (f.subcategoria) params.set('subcategoria',f.subcategoria);
  if (f.sla)          params.set('sla',f.sla);
  if (f.status)       params.set('status',f.status);

  const tbody = document.getElementById('tabela-body');
  tbody.innerHTML = '<tr><td colspan="9" class="empty-state">Carregando…</td></tr>';

  try {
    const res = await fetch(`${API}/emails?${params}`, { headers: headers() });
    if (!res.ok) { tbody.innerHTML='<tr><td colspan="9" class="empty-state" style="color:#E24B4A">Erro ao carregar.</td></tr>'; return; }
    const data = await res.json();

    totalPaginas = data.paginas||1;
    document.getElementById('badge-total').textContent = `${data.total} e-mail${data.total!==1?'s':''}`;
    document.getElementById('badge-total').style.display = 'inline-block';

    const pag = document.getElementById('paginacao');
    if (data.total>0) {
      pag.classList.add('show');
      document.getElementById('pag-info').textContent = `Página ${paginaAtual} de ${totalPaginas} — ${data.total} registros`;
      document.getElementById('btn-prev').disabled = paginaAtual<=1;
      document.getElementById('btn-next').disabled = paginaAtual>=totalPaginas;
    } else pag.classList.remove('show');

    if (!data.items.length) { tbody.innerHTML='<tr><td colspan="9" class="empty-state">Nenhum e-mail encontrado.</td></tr>'; return; }

    const contaMap = Object.fromEntries(todasContas.map(c=>[c.id, c.nome]));

    tbody.innerHTML = data.items.map(e => {
      const borderGerencial = e.gerencial==='sim' ? 'border-left:2px solid #E24B4A;' : '';
      const nomeConta = e.conta_id ? (contaMap[e.conta_id]||`#${e.conta_id}`) : '—';
      return `
      <tr style="${borderGerencial}cursor:pointer" data-email-id="${e.id}">
        <td style="white-space:nowrap">${fmtData(e.data_recebimento)}</td>
        <td>${truncar(nomeConta,18)}</td>
        <td>${iconeGerencial(e.gerencial)} ${truncar(e.remetente,24)}</td>
        <td><strong>${truncar(e.assunto,42)}</strong></td>
        <td class="center">${badgeCategoria(e.categoria)}</td>
        <td class="center" style="font-size:12px">${truncar(e.subcategoria,24)||'—'}</td>
        <td class="center">${badgeSla(e.sla)}</td>
        <td class="center">${badgeStatus(e.status)}</td>
        <td class="center">
          <button class="btn-ver" data-email-id="${e.id}">✎</button>
        </td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-state" style="color:#E24B4A">Erro: ${err.message}</td></tr>`;
  }
}

// ── Modal Detalhe ──────────────────────────────────────────────────────────
async function abrirDetalhe(id) {
  emailDetalheId = id;
  try {
    const res = await fetch(`${API}/emails/${id}`, { headers: headers() });
    if (!res.ok) { toast('Erro ao carregar detalhe','erro'); return; }
    const e = await res.json();
    document.getElementById('det-assunto').textContent   = e.assunto;
    document.getElementById('det-remetente').textContent = e.remetente;
    document.getElementById('det-data').textContent      = fmtData(e.data_recebimento);
    document.getElementById('det-corpo').textContent     = e.corpo || '(corpo vazio)';
    document.getElementById('det-categoria').value  = e.categoria || '';
    document.getElementById('det-sla').value        = e.sla || '';
    document.getElementById('det-gerencial').value  = e.gerencial || 'nao';
    document.getElementById('det-status').value     = e.status || 'novo';
    const gb = document.getElementById('det-gerencial-badge');
    e.gerencial==='sim' ? gb.classList.remove('hidden') : gb.classList.add('hidden');
    atualizarSubcategoriasModal();
    document.getElementById('det-subcategoria').value = e.subcategoria || '';
    document.getElementById('modal-detalhe').classList.remove('hidden');
  } catch (err) { toast('Erro: '+err.message,'erro'); }
}
function fecharDetalhe() { document.getElementById('modal-detalhe').classList.add('hidden'); emailDetalheId=null; }

async function salvarClassificacao() {
  if (!emailDetalheId) return;
  const payload = {
    categoria:    document.getElementById('det-categoria').value||null,
    subcategoria: document.getElementById('det-subcategoria').value||null,
    sla:          document.getElementById('det-sla').value||null,
    gerencial:    document.getElementById('det-gerencial').value,
    status:       document.getElementById('det-status').value,
  };
  try {
    const res = await fetch(`${API}/emails/${emailDetalheId}`, { method:'PUT', headers: headers(), body:JSON.stringify(payload) });
    if (!res.ok) { toast('Erro ao salvar','erro'); return; }
    toast('Classificação salva!','ok'); fecharDetalhe(); carregarEmails(); verificarPendentes();
  } catch (err) { toast('Erro: '+err.message,'erro'); }
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { fecharDetalhe(); fecharModalTreinar(); fecharModalProgresso(); }
});

// ── Init ───────────────────────────────────────────────────────────────────
(async () => {
  // Nav sidebar
  document.getElementById('nav-treinar').addEventListener('click', abrirModalTreinar);
  document.getElementById('nav-exportar').addEventListener('click', exportarDataset);

  // Toolbar
  document.getElementById('btn-extrair').addEventListener('click', executarExtracao);
  document.getElementById('btn-classificar').addEventListener('click', executarClassificacao);
  document.getElementById('campo-busca').addEventListener('input', aplicarFiltros);
  document.getElementById('btn-limpar-filtros').addEventListener('click', limparFiltros);

  // Filtros
  document.getElementById('filtro-conta').addEventListener('change', aplicarFiltros);
  document.getElementById('filtro-categoria').addEventListener('change', aplicarFiltros);
  document.getElementById('filtro-subcategoria').addEventListener('change', aplicarFiltros);
  document.getElementById('filtro-sla').addEventListener('change', aplicarFiltros);
  document.getElementById('filtro-status').addEventListener('change', aplicarFiltros);

  // Paginação
  document.getElementById('btn-prev').addEventListener('click', () => mudarPagina(-1));
  document.getElementById('btn-next').addEventListener('click', () => mudarPagina(1));

  // Logout
  document.getElementById('btn-logout').addEventListener('click', fazerLogout);

  // Modal Progresso
  document.getElementById('btn-fechar-progresso').addEventListener('click', fecharModalProgresso);
  document.getElementById('btn-fechar-progresso-rodape').addEventListener('click', fecharModalProgresso);

  // Modal Treinar
  document.getElementById('btn-fechar-treinar').addEventListener('click', fecharModalTreinar);
  document.getElementById('btn-fechar-treinar-rodape').addEventListener('click', fecharModalTreinar);
  document.getElementById('btn-confirmar-treinar').addEventListener('click', executarTreinamento);

  // Modal Detalhe
  document.getElementById('btn-fechar-detalhe').addEventListener('click', fecharDetalhe);
  document.getElementById('btn-fechar-detalhe-rodape').addEventListener('click', fecharDetalhe);
  document.getElementById('btn-salvar-classificacao').addEventListener('click', salvarClassificacao);
  document.getElementById('det-categoria').addEventListener('change', atualizarSubcategoriasModal);

  // Event delegation — tabela de e-mails
  document.getElementById('tabela-body').addEventListener('click', e => {
    const btn = e.target.closest('button[data-email-id]');
    const row = e.target.closest('tr[data-email-id]');
    if (btn) { e.stopPropagation(); abrirDetalhe(parseInt(btn.dataset.emailId)); }
    else if (row) abrirDetalhe(parseInt(row.dataset.emailId));
  });

  await checarAuth();
  await carregarContas();
  verificarModelo();
  verificarPendentes();
  carregarSubcategorias();
  carregarEmails();
})();
