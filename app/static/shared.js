// Compartilhado entre todas as páginas: auth + header + nav.

function authHeaders() {
  const t = sessionStorage.getItem('lidia_token');
  return t ? { 'Authorization': 'Bearer ' + t } : {};
}

async function doLogin() {
  const user = document.getElementById('loginUser').value;
  const pass = document.getElementById('loginPass').value;
  const err = document.getElementById('loginError');
  err.style.display = 'none';
  try {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass }),
    });
    if (!r.ok) {
      err.textContent = 'Usuário ou senha incorretos';
      err.style.display = '';
      return;
    }
    const d = await r.json();
    sessionStorage.setItem('lidia_token', d.access_token);
    sessionStorage.setItem('lidia_user', d.username);
    onAuthReady();
  } catch (e) {
    err.textContent = 'Erro de conexão';
    err.style.display = '';
  }
}

function doLogout() {
  sessionStorage.clear();
  location.href = '/';
}

function isAuthed() {
  return !!sessionStorage.getItem('lidia_token');
}

// Cada página implementa onAuthReady() para esconder login e mostrar conteúdo.
function defaultAuthReady() {
  const overlay = document.getElementById('loginOverlay');
  const header = document.getElementById('mainHeader');
  if (overlay) overlay.style.display = 'none';
  if (header) header.style.display = '';
  const userEl = document.getElementById('userName');
  if (userEl) userEl.textContent = sessionStorage.getItem('lidia_user') || '';
}

window.onAuthReady = window.onAuthReady || defaultAuthReady;

// AUTO-LOGIN DEV — REMOVER ANTES DE PRODUÇÃO.
async function _autoLoginDev() {
  if (isAuthed()) return true;
  try {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'jE7eVjKE1YJ10Xu6Oyrx' }),
    });
    if (!r.ok) return false;
    const d = await r.json();
    sessionStorage.setItem('lidia_token', d.access_token);
    sessionStorage.setItem('lidia_user', d.username);
    return true;
  } catch (e) {
    return false;
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await _autoLoginDev();
  if (isAuthed()) onAuthReady();
  const passEl = document.getElementById('loginPass');
  if (passEl) passEl.addEventListener('keyup', (e) => { if (e.key === 'Enter') doLogin(); });
});

// Marca tab ativa no header com base no path.
function highlightActiveNav() {
  const path = location.pathname;
  document.querySelectorAll('.tab-btn').forEach((b) => {
    const href = b.getAttribute('href') || '';
    b.classList.toggle('active', href === path || (path === '/' && b.dataset.tab === 'home'));
  });
}
document.addEventListener('DOMContentLoaded', highlightActiveNav);
