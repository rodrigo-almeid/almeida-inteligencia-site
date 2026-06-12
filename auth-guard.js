/**
 * Auth Guard — verificação de token + logout por inatividade
 * Inclua este script antes do </body> nas páginas protegidas.
 *
 * Configurações:
 *   INACTIVITY_LIMIT  — minutos sem atividade até logout  (padrão: 30)
 *   WARN_BEFORE       — segundos de aviso antes do logout  (padrão: 60)
 *   CHECK_INTERVAL    — segundos entre verificações do token (padrão: 30)
 */
(function () {
  const INACTIVITY_LIMIT = 30 * 60 * 1000; // 30 min em ms
  const WARN_BEFORE      = 60 * 1000;       // aviso 60 s antes
  const CHECK_INTERVAL   = 30 * 1000;       // checa token a cada 30 s

  /* ── Estilos do toast ── */
  const style = document.createElement('style');
  style.textContent = `
    #auth-toast {
      position: fixed; bottom: 32px; left: 50%; transform: translateX(-50%);
      background: #1A241C; border: 1px solid rgba(226,75,74,0.5);
      color: #fff; font-family: 'Inter', sans-serif; font-size: 14px;
      padding: 14px 24px; border-radius: 12px; z-index: 9999;
      display: flex; align-items: center; gap: 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
      opacity: 0; transition: opacity .3s; pointer-events: none;
    }
    #auth-toast.visible { opacity: 1; pointer-events: auto; }
    #auth-toast .toast-msg { flex: 1; }
    #auth-toast .toast-timer { font-size: 20px; font-weight: 700; color: #E24B4A; min-width: 32px; text-align: center; }
    #auth-toast .toast-btn {
      background: #3DDB82; color: #0A0F0A; border: none; border-radius: 8px;
      font-size: 13px; font-weight: 600; font-family: 'Inter', sans-serif;
      padding: 8px 16px; cursor: pointer;
    }
    #auth-toast .toast-btn:hover { opacity: .85; }
  `;
  document.head.appendChild(style);

  /* ── Toast DOM ── */
  const toast = document.createElement('div');
  toast.id = 'auth-toast';
  toast.innerHTML = `
    <span class="toast-msg">Sessão expirando por inatividade</span>
    <span class="toast-timer" id="ag-countdown">60</span>
    <button class="toast-btn" onclick="authGuard.keepAlive()">Continuar</button>
  `;
  document.body.appendChild(toast);

  /* ── Estado ── */
  let lastActivity   = Date.now();
  let warnTimer      = null;
  let countdownTimer = null;
  let tokenCheckInt  = null;
  let secondsLeft    = 0;

  /* ── Funções públicas ── */
  window.authGuard = {
    keepAlive() {
      lastActivity = Date.now();
      hideToast();
      scheduleWarn();
    }
  };

  function getToken() { return localStorage.getItem('admin_token'); }

  function forceLogout(reason) {
    clearTimers();
    localStorage.clear();
    sessionStorage.setItem('logout_reason', reason || 'sessão expirada');
    window.location.href = '/';
  }

  function checkToken() {
    const token = getToken();
    if (!token) { forceLogout('token ausente'); return; }
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      if (payload.exp && Date.now() / 1000 > payload.exp) {
        forceLogout('token expirado');
      }
    } catch (e) { forceLogout('token inválido'); }
  }

  /* ── Toast de aviso ── */
  function showToast() {
    secondsLeft = Math.round(WARN_BEFORE / 1000);
    document.getElementById('ag-countdown').textContent = secondsLeft;
    toast.classList.add('visible');

    countdownTimer = setInterval(() => {
      secondsLeft--;
      document.getElementById('ag-countdown').textContent = secondsLeft;
      if (secondsLeft <= 0) {
        clearInterval(countdownTimer);
        forceLogout('inatividade');
      }
    }, 1000);
  }

  function hideToast() {
    toast.classList.remove('visible');
    clearInterval(countdownTimer);
    countdownTimer = null;
  }

  /* ── Agendamento ── */
  function scheduleWarn() {
    clearTimeout(warnTimer);
    warnTimer = setTimeout(() => {
      if (toast.classList.contains('visible')) return; // já está mostrando
      showToast();
    }, INACTIVITY_LIMIT - WARN_BEFORE);
  }

  function clearTimers() {
    clearTimeout(warnTimer);
    clearInterval(countdownTimer);
    clearInterval(tokenCheckInt);
  }

  /* ── Detecção de atividade ── */
  ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'].forEach(ev => {
    document.addEventListener(ev, () => {
      if (Date.now() - lastActivity < 5000) return; // debounce 5 s
      lastActivity = Date.now();
      if (toast.classList.contains('visible')) hideToast();
      scheduleWarn();
    }, { passive: true });
  });

  /* ── Visibilidade da aba: checa token ao voltar ── */
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') checkToken();
  });

  /* ── Init ── */
  checkToken();
  scheduleWarn();
  tokenCheckInt = setInterval(checkToken, CHECK_INTERVAL);
})();
