console.log("nova_senha.js carregado!");

const form = document.getElementById('redefinir-senha-form');
const message = document.getElementById('message');
const submitBtn = form.querySelector('button[type="submit"]');

function getTokenFromURL() {
  const params = new URLSearchParams(window.location.search);
  return (params.get('token') || '').trim();
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  const novaSenha = document.getElementById('nova-senha').value.trim();
  const repetirSenha = document.getElementById('repetir-senha').value.trim();
  const token = getTokenFromURL();

  if (!token) {
    message.textContent = 'Link inválido ou expirado.';
    message.style.color = 'red';
    return;
  }
  if (novaSenha.length < 8) {
    message.textContent = 'A senha deve ter pelo menos 8 caracteres.';
    message.style.color = 'red';
    return;
  }
  if (novaSenha !== repetirSenha) {
    message.textContent = 'As senhas não coincidem. Por favor, corrija e tente novamente.';
    message.style.color = 'red';
    return;
  }

  message.textContent = 'Enviando...';
  message.style.color = 'navy';
  submitBtn.disabled = true;

  try {
    const resp = await fetch('/nova_senha', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, novaSenha })
    });

    let data = {};
    try {
      data = await resp.json();
    } catch {
      // se o backend retornou texto puro
      data = { success: resp.ok, message: resp.ok ? 'Senha atualizada.' : 'Falha ao atualizar senha.' };
    }

    if (resp.ok && data.success) {
      message.textContent = data.message || 'Senha atualizada com sucesso!';
      message.style.color = 'green';
      // redireciona após 1.5s (opcional)
      setTimeout(() => { window.location.href = '/'; }, 1500);
    } else {
      message.textContent = data.message || 'Link inválido ou expirado.';
      message.style.color = 'red';
    }
  } catch (error) {
    console.error('Erro:', error);
    message.textContent = 'Erro ao conectar com o servidor.';
    message.style.color = 'red';
  } finally {
    submitBtn.disabled = false;
  }
});
