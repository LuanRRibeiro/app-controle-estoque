// static/js/login.js
console.log("login.js carregado!");

const form = document.getElementById('login-form');
const emailEl = document.getElementById('email');
const passEl  = document.getElementById('password');
const rememberEl = document.getElementById('remember');

const errorBox = document.getElementById('error-message');
const spinner  = document.getElementById('loading-spinner');
const submitBtn = form.querySelector('button[type="submit"]');

function setLoading(on) {
  spinner.style.display = on ? 'block' : 'none';
  submitBtn.disabled = !!on;
}
function showError(msg) {
  errorBox.textContent = msg || '';
}
function clearError() {
  showError('');
}

form.addEventListener('submit', function (event) {
  event.preventDefault();
  clearError();
  setLoading(true);

  const formData = new FormData(form);
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/');

  xhr.onload = function () {
    let response = {};
    try { response = JSON.parse(xhr.responseText || '{}'); } catch (_) {}

    if (xhr.status === 200) {
      if (response && response.error === null) {
        // sucesso
        salvarCredenciais();
        setLoading(false); // esconde antes de redirecionar (caso demore)
        window.location.href = '/painel';
        return;
      } else {
        // credenciais inválidas ou erro do backend
        showError(response.error || 'Falha na conexão. Tente novamente.');
        passEl.value = '';
      }
    } else {
      // <<< AQUI era o bug: spinner não escondia em status != 200
      showError('Falha na conexão. Tente novamente.');
    }
    setLoading(false); // SEMPRE esconder ao final deste handler
  };

  xhr.onerror = function () {
    showError('Problema de rede. Verifique sua conexão.');
    setLoading(false);
  };

  xhr.ontimeout = function () {
    showError('Tempo esgotado. Tente novamente.');
    setLoading(false);
  };

  xhr.send(formData);
});

// Limpa erro quando o usuário digita
emailEl.addEventListener('input', clearError);
passEl.addEventListener('input', clearError);

// Salva email e senha se o login for bem-sucedido (⚠️ salvar senha em localStorage não é recomendado)
function salvarCredenciais() {
  const email = emailEl.value;
  const senha = passEl.value;
  const lembrarMe = rememberEl.checked;

  if (lembrarMe) {
    localStorage.setItem('email', email);
  } else {
    localStorage.removeItem('email');
  }

  // higiene: garante que nunca fique senha guardada
  localStorage.removeItem('senha');
}


// Preencher o e-mail ao carregar
window.addEventListener('DOMContentLoaded', () => {
  const emailSalvo = localStorage.getItem('email');
  if (emailSalvo) {
    document.getElementById('email').value = emailSalvo;
    document.getElementById('remember').checked = true;}});
