const API = '/email/api';
let paginaAtual = 1;
let totalPaginas = 1;
let emailDetalheId = null;
let todasSubcategorias = [];
let todasContas = [];
let contaEditandoId = null;

const SUBCATS_POR_CAT = {
  "VT": ["Compra de VT – Admissão","Compra de VT – Extra","Vínculo de carga ao cartão",
         "Gestão de saldo","2ª via de cartão VT","Comunicados da operadora VT","Emails gerenciais – VT"],
  "VR": ["Compra de VR","2ª via de cartão VR"],
  "Outros": ["Recebimento de boleto","Recebimento de NF","Não classificado"],
};

const IMAP_SERVIDORES = {
  gmail:   { server: "imap.gmail.com",           port: 993 },
  outlook: { server: "outlook.office365.com",     port: 993 },
  other:   { server: "",                          port: 993 },
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
    document.getElementById('sidebar-usuario').textContent = u.nome;
  } catch (_) { fazerLogout(); }
}

// ── Toast ──────────────────────────────────────────────────────────────────
let _toastTimer = null;
function toast(msg, tipo = 'ok') {
  const el = document.getElementById('toast');
  const msgEl = document.getElementById('toast-msg');
  const cor = tipo === 'ok' ? 'text-green-400' : tipo === 'erro' ? 'text-red-400' : 'text-yellow-400';
  const icone = tipo === 'ok' ? 'fa-circle-check' : tipo === 'erro' ? 'fa-circle-xmark' : 'fa-circle-info';
  msgEl.innerHTML = `<i class="fa-solid ${icone} ${cor}"></i> ${msg}`;
  el.classList.remove('hidden');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add('hidden'), 4000);
}

// ── Badges ─────────────────────────────────────────────────────────────────
function badgeSla(v) {
  if (!v) return '<span class="text-gray-600 text-xs">—</span>';
  const map = { 'D+0':'bg-red-900 text-red-300 border border-red-700','D+1':'bg-orange-900 text-orange-300',
                'D+2':'bg-yellow-900 text-yellow-300','D+3+':'bg-gray-800 text-gray-400' };
  return `<span class="text-xs px-2 py-0.5 rounded-full font-bold ${map[v]||'bg-gray-800 text-gray-300'}">${v}</span>`;
}
function badgeCategoria(v) {
  if (!v) return '<span class="text-gray-600 text-xs">—</span>';
  const map = { 'VT':'bg-blue-900 text-blue-300','VR':'bg-purple-900 text-purple-300','Outros':'bg-gray-800 text-gray-300' };
  return `<span class="text-xs px-2 py-0.5 rounded-full font-medium ${map[v]||'bg-gray-800 text-gray-300'}">${v}</span>`;
}
function badgeStatus(v) {
  const map = { 'novo':'bg-blue-900 text-blue-300','classificado':'bg-emerald-900 text-emerald-300',
                'nao_classificado':'bg-red-900 text-red-300','tratado':'bg-green-900 text-green-300',
                'ignorado':'bg-gray-800 text-gray-400' };
  const label = { 'nao_classificado':'não classif.' };
  return `<span class="text-xs px-2 py-0.5 rounded-full font-medium ${map[v]||'bg-gray-800 text-gray-300'}">${label[v]||v}</span>`;
}
function iconeGerencial(v) {
  return v==='sim' ? '<i class="fa-solid fa-circle-exclamation text-red-400" title="Gerencial"></i>' : '';
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
  document.getElementById('progresso-rodape').classList.add('hidden');
  document.getElementById('progresso-titulo').textContent = titulo;
  document.getElementById('progresso-icone').className = `fa-solid ${icone} ${corBtn}`;
  document.getElementById('progresso-pill').textContent = 'em andamento…';
  document.getElementById('progresso-pill').className = 'text-xs text-gray-500 animate-pulse';
  document.getElementById('progresso-btn-fechar').className =
    `px-4 py-2 ${corBtn.includes('purple') ? 'bg-purple-600 hover:bg-purple-500' : 'bg-indigo-600 hover:bg-indigo-500'} text-white text-sm rounded-lg transition`;
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
      document.getElementById('progresso-rodape').classList.remove('hidden');
      return;
    }
    try {
      const res = await fetch(`${API}/job/${jobId}`, { headers: headers() });
      const job = await res.json();

      const novas = (job.progresso || []).slice(visto);
      novas.forEach(p => {
        const t = ICONE_TIPO[p.tipo] || ICONE_TIPO.info;
        const div = document.createElement('div');
        div.className = 'flex items-start gap-2 py-1 border-b border-gray-800/50';
        div.innerHTML = `<i class="fa-solid ${t.icon} ${t.cor} mt-0.5 shrink-0 text-xs"></i><span class="text-xs text-gray-300 leading-relaxed">${p.msg}</span>`;
        logEl.appendChild(div);
      });
      visto += novas.length;
      logEl.scrollTop = logEl.scrollHeight;

      if (job.status === 'concluido') {
        clearInterval(poll);
        pill.textContent = 'concluído';
        pill.classList.remove('animate-pulse');
        document.getElementById('progresso-rodape').classList.remove('hidden');
        onConcluido(job.resultado);
      } else if (job.status === 'erro') {
        clearInterval(poll);
        pill.textContent = 'erro';
        pill.classList.remove('animate-pulse');
        document.getElementById('progresso-rodape').classList.remove('hidden');
        toast('Erro: ' + (job.erro || 'desconhecido'), 'erro');
      }
    } catch (_) {}
  }, 1000);
}

// ── Extração ───────────────────────────────────────────────────────────────
async function executarExtracao() {
  const btn = document.getElementById('btn-extrair');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Extraindo…';
  abrirModalProgresso('Extraindo E-mails', 'fa-download', 'text-indigo-400');

  try {
    const res = await fetch(`${API}/extrair`, { method: 'POST', headers: headers() });
    const data = await res.json();
    if (!res.ok) { fecharModalProgresso(); toast(data.detail || 'Erro na extração.', 'erro'); }
    else _iniciarPolling(data.job_id, (r) => {
      if (r) toast(`${r.extraidos} importado(s)${r.ignorados_duplicados ? ` · ${r.ignorados_duplicados} duplicado(s)` : ''}`, 'ok');
      carregarEmails(); verificarPendentes();
    });
  } catch (err) { fecharModalProgresso(); toast('Erro: ' + err.message, 'erro'); }
  finally { btn.disabled=false; btn.innerHTML='<i class="fa-solid fa-download"></i> Extrair E-mails'; }
}

// ── Classificação ──────────────────────────────────────────────────────────
async function executarClassificacao() {
  const btn = document.getElementById('btn-classificar');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Classificando…';
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
  finally { btn.disabled=false; btn.innerHTML='<i class="fa-solid fa-brain"></i> Classificar E-mails'; }
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
    if (pendentes > 0) { badge.textContent = `${pendentes} aguardando classificação`; badge.classList.remove('hidden'); }
    else badge.classList.add('hidden');
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
      badge.className = 'text-xs px-2.5 py-1 rounded-full font-medium bg-emerald-900 text-emerald-300';
      btn.disabled = false;
      btn.classList.remove('opacity-50','cursor-not-allowed');
      btn.title = '';
    } else {
      badge.textContent = 'IA não treinada';
      badge.className = 'text-xs px-2.5 py-1 rounded-full font-medium bg-gray-800 text-gray-400';
      btn.disabled = true;
      btn.classList.add('opacity-50','cursor-not-allowed');
      btn.title = 'Treine o modelo antes de classificar';
    }
    badge.classList.remove('hidden');
  } catch (_) {}
}

// ── Modal Treinar ───────────────────────────────────────────────────────────
function abrirModalTreinar() { document.getElementById('treinar-status').classList.add('hidden'); document.getElementById('modal-treinar').classList.remove('hidden'); }
function fecharModalTreinar() { document.getElementById('modal-treinar').classList.add('hidden'); }
async function executarTreinamento() {
  const btn = document.getElementById('btn-confirmar-treinar');
  const statusEl = document.getElementById('treinar-status');
  btn.disabled=true; btn.innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Treinando…';
  try {
    const res = await fetch(`${API}/treinar`, { method:'POST', headers: headers() });
    const data = await res.json();
    if (!res.ok) { toast(data.detail||'Erro.','erro'); return; }
    let html='';
    for (const [alvo, info] of Object.entries(data)) {
      if (info.status==='insuficiente')
        html+=`<div class="text-yellow-400 flex gap-2"><i class="fa-solid fa-triangle-exclamation mt-0.5"></i><span><b>${alvo}</b>: insuficiente (${info.amostras} amostras, mín. 5)</span></div>`;
      else {
        html+=`<div class="text-emerald-400 flex gap-2"><i class="fa-solid fa-circle-check mt-0.5"></i><span><b>${alvo}</b>: ${(info.acuracia*100).toFixed(1)}% — ${info.amostras_treino} treino / ${info.amostras_teste} teste</span></div>`;
        html+=`<div class="text-xs text-gray-400 pl-6">Classes: ${info.classes.join(', ')}</div>`;
      }
    }
    statusEl.innerHTML=html; statusEl.classList.remove('hidden');
    toast('Treinamento concluído!','ok'); verificarModelo();
  } catch (err) { toast('Erro: '+err.message,'erro'); }
  finally { btn.disabled=false; btn.innerHTML='<i class="fa-solid fa-brain"></i> Iniciar Treinamento'; }
}

// ── Contas IMAP ────────────────────────────────────────────────────────────
async function carregarContas() {
  try {
    const res = await fetch(`${API}/contas`, { headers: headers() });
    if (!res.ok) return;
    todasContas = await res.json();

    // Atualiza aviso sem conta
    const aviso = document.getElementById('aviso-sem-conta');
    todasContas.filter(c=>c.ativo).length === 0 ? aviso.classList.remove('hidden') : aviso.classList.add('hidden');

    // Atualiza filtro de contas
    const sel = document.getElementById('filtro-conta');
    sel.innerHTML = '<option value="">Todas as contas</option>';
    todasContas.forEach(c => {
      const o=document.createElement('option'); o.value=c.id; o.textContent=c.nome; sel.appendChild(o);
    });
  } catch (_) {}
}

function abrirModalContas() {
  renderizarListaContas();
  document.getElementById('modal-contas').classList.remove('hidden');
}
function fecharModalContas() { document.getElementById('modal-contas').classList.add('hidden'); }

function renderizarListaContas() {
  const el = document.getElementById('lista-contas');
  if (!todasContas.length) {
    el.innerHTML = '<p class="text-gray-500 text-sm text-center py-4">Nenhuma conta cadastrada.</p>';
    return;
  }
  el.innerHTML = todasContas.map(c => `
    <div class="bg-gray-800 rounded-xl p-4 flex items-center gap-3">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <span class="font-medium text-sm">${c.nome}</span>
          <span class="text-xs px-1.5 py-0.5 rounded ${c.provider==='gmail'?'bg-red-900 text-red-300':'bg-blue-900 text-blue-300'}">${c.provider}</span>
          ${c.ativo ? '' : '<span class="text-xs bg-gray-700 text-gray-400 px-1.5 py-0.5 rounded">inativo</span>'}
        </div>
        <p class="text-xs text-gray-400 mt-0.5 truncate">${c.email}</p>
        <p class="text-xs text-gray-600">${c.imap_server}:${c.imap_port}</p>
      </div>
      <div class="flex gap-1 flex-shrink-0">
        <button onclick="testarConta(${c.id}, this)" title="Testar conexão IMAP"
          class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-700 text-yellow-400 transition">
          <i class="fa-solid fa-plug text-xs"></i>
        </button>
        <button onclick="toggleAtivoConta(${c.id})" title="${c.ativo?'Desativar':'Ativar'}"
          class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-700 transition ${c.ativo?'text-green-400':'text-gray-500'}">
          <i class="fa-solid ${c.ativo?'fa-toggle-on':'fa-toggle-off'}"></i>
        </button>
        <button onclick="editarConta(${c.id})" title="Editar"
          class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-700 text-indigo-400 transition">
          <i class="fa-solid fa-pen-to-square text-xs"></i>
        </button>
        <button onclick="removerConta(${c.id})" title="Remover"
          class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-700 text-red-400 transition">
          <i class="fa-solid fa-trash text-xs"></i>
        </button>
      </div>
    </div>`).join('');
}

function abrirFormConta(conta = null) {
  contaEditandoId = conta ? conta.id : null;
  document.getElementById('form-conta-titulo').textContent = conta ? 'Editar Conta IMAP' : 'Nova Conta IMAP';
  document.getElementById('fc-nome').value     = conta ? conta.nome : '';
  document.getElementById('fc-provider').value = conta ? conta.provider : 'gmail';
  document.getElementById('fc-email').value    = conta ? conta.email : '';
  document.getElementById('fc-password').value = '';
  document.getElementById('fc-server').value   = conta ? conta.imap_server : 'imap.gmail.com';
  document.getElementById('fc-port').value     = conta ? conta.imap_port : 993;
  document.getElementById('fc-erro').classList.add('hidden');
  document.getElementById('modal-form-conta').classList.remove('hidden');
}
function fecharFormConta() { document.getElementById('modal-form-conta').classList.add('hidden'); contaEditandoId=null; }

function preencherServidorPadrao() {
  const prov = document.getElementById('fc-provider').value;
  const cfg = IMAP_SERVIDORES[prov];
  if (cfg && cfg.server) {
    document.getElementById('fc-server').value = cfg.server;
    document.getElementById('fc-port').value   = cfg.port;
  }
}
function toggleSenhaForm() {
  const inp = document.getElementById('fc-password');
  const ico = document.getElementById('fc-eye');
  inp.type = inp.type==='password' ? 'text' : 'password';
  ico.className = inp.type==='password' ? 'fa-solid fa-eye text-sm' : 'fa-solid fa-eye-slash text-sm';
}

async function salvarConta() {
  const nome     = document.getElementById('fc-nome').value.trim();
  const provider = document.getElementById('fc-provider').value;
  const email    = document.getElementById('fc-email').value.trim();
  const password = document.getElementById('fc-password').value.trim();
  const server   = document.getElementById('fc-server').value.trim();
  const port     = parseInt(document.getElementById('fc-port').value);
  const erroEl   = document.getElementById('fc-erro');

  if (!nome || !email || !server || !port) { erroEl.textContent='Preencha todos os campos.'; erroEl.classList.remove('hidden'); return; }
  if (!contaEditandoId && !password) { erroEl.textContent='Informe a senha/App Password.'; erroEl.classList.remove('hidden'); return; }

  const body = { nome, provider, email, imap_server:server, imap_port:port, password: password || '___unchanged___' };
  const url  = contaEditandoId ? `${API}/contas/${contaEditandoId}` : `${API}/contas`;
  const method = contaEditandoId ? 'PUT' : 'POST';

  try {
    const res = await fetch(url, { method, headers: headers(), body: JSON.stringify(body) });
    if (!res.ok) { const e=await res.json(); erroEl.textContent=e.detail||'Erro.'; erroEl.classList.remove('hidden'); return; }
    fecharFormConta();
    await carregarContas();
    renderizarListaContas();
    toast(contaEditandoId ? 'Conta atualizada!' : 'Conta adicionada!', 'ok');
  } catch (_) { erroEl.textContent='Erro de conexão.'; erroEl.classList.remove('hidden'); }
}

function editarConta(id) {
  const conta = todasContas.find(c=>c.id===id);
  if (conta) abrirFormConta(conta);
}

async function toggleAtivoConta(id) {
  try {
    const res = await fetch(`${API}/contas/${id}/ativo`, { method:'PATCH', headers: headers() });
    if (!res.ok) return;
    await carregarContas();
    renderizarListaContas();
  } catch (_) {}
}

async function removerConta(id) {
  if (!confirm('Remover esta conta? Os e-mails já importados não serão apagados.')) return;
  try {
    await fetch(`${API}/contas/${id}`, { method:'DELETE', headers: headers() });
    await carregarContas();
    renderizarListaContas();
    toast('Conta removida.', 'ok');
  } catch (_) {}
}

async function testarConta(id, btn) {
  const ico = btn.querySelector('i');
  const orig = ico.className;
  ico.className = 'fa-solid fa-spinner fa-spin text-xs';
  btn.disabled = true;
  try {
    const res = await fetch(`${API}/contas/${id}/testar`, { method: 'POST', headers: headers() });
    const data = await res.json();
    toast(data.msg, data.ok ? 'ok' : 'erro');
    ico.className = data.ok ? 'fa-solid fa-plug text-xs text-green-400' : 'fa-solid fa-plug text-xs text-red-400';
    setTimeout(() => { ico.className = orig; btn.disabled = false; }, 3000);
  } catch (_) {
    toast('Erro ao testar conexão.', 'erro');
    ico.className = orig;
    btn.disabled = false;
  }
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
  tbody.innerHTML = '<tr><td colspan="9" class="text-center py-16 text-gray-500"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Carregando...</td></tr>';

  try {
    const res = await fetch(`${API}/emails?${params}`, { headers: headers() });
    if (!res.ok) { tbody.innerHTML='<tr><td colspan="9" class="text-center py-16 text-red-400">Erro ao carregar.</td></tr>'; return; }
    const data = await res.json();

    totalPaginas = data.paginas||1;
    document.getElementById('badge-total').textContent = `${data.total} e-mail${data.total!==1?'s':''}`;
    document.getElementById('badge-total').classList.remove('hidden');

    const pag = document.getElementById('paginacao');
    if (data.total>0) {
      pag.classList.remove('hidden');
      document.getElementById('pag-info').textContent = `Página ${paginaAtual} de ${totalPaginas} — ${data.total} registros`;
      document.getElementById('btn-prev').disabled = paginaAtual<=1;
      document.getElementById('btn-next').disabled = paginaAtual>=totalPaginas;
    } else pag.classList.add('hidden');

    if (!data.items.length) { tbody.innerHTML='<tr><td colspan="9" class="text-center py-16 text-gray-500">Nenhum e-mail encontrado.</td></tr>'; return; }

    const contaMap = Object.fromEntries(todasContas.map(c=>[c.id, c.nome]));

    tbody.innerHTML = data.items.map(e => {
      const rowClass = e.gerencial==='sim' ? 'border-l-2 border-red-600' : '';
      const nomeConta = e.conta_id ? (contaMap[e.conta_id]||`#${e.conta_id}`) : '—';
      return `
      <tr class="border-b border-gray-800 hover:bg-gray-800/40 transition cursor-pointer ${rowClass}" onclick="abrirDetalhe(${e.id})">
        <td class="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">${fmtData(e.data_recebimento)}</td>
        <td class="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">${truncar(nomeConta,18)}</td>
        <td class="px-4 py-3 text-sm max-w-[140px]">
          <div class="flex items-center gap-1.5">${iconeGerencial(e.gerencial)}<span class="truncate block" title="${e.remetente}">${truncar(e.remetente,24)}</span></div>
        </td>
        <td class="px-4 py-3 text-sm max-w-[200px]"><span class="truncate block" title="${e.assunto}">${truncar(e.assunto,42)}</span></td>
        <td class="px-4 py-3 text-center">${badgeCategoria(e.categoria)}</td>
        <td class="px-4 py-3 text-center max-w-[140px]"><span class="text-xs text-gray-300">${truncar(e.subcategoria,24)}</span></td>
        <td class="px-4 py-3 text-center">${badgeSla(e.sla)}</td>
        <td class="px-4 py-3 text-center">${badgeStatus(e.status)}</td>
        <td class="px-4 py-3 text-center">
          <button onclick="event.stopPropagation();abrirDetalhe(${e.id})"
            class="text-indigo-400 hover:text-indigo-300 text-xs px-2 py-1 rounded hover:bg-indigo-900/30 transition">
            <i class="fa-solid fa-pen-to-square"></i>
          </button>
        </td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center py-16 text-red-400">Erro: ${err.message}</td></tr>`;
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
  if (e.key==='Escape') { fecharDetalhe(); fecharModalContas(); fecharFormConta(); fecharModalTreinar(); fecharModalProgresso(); }
});

// ── Init ───────────────────────────────────────────────────────────────────
(async () => {
  await checarAuth();
  await carregarContas();
  verificarModelo();
  verificarPendentes();
  carregarSubcategorias();
  carregarEmails();
})();
