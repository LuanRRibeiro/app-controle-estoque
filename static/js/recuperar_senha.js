const form = document.querySelector('form');
const emailInput = document.getElementById('email');
const message = document.getElementById('message');
const submitBtn = form.querySelector('button[type="submit"]');

form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const email = emailInput.value.trim();

    // Validação simples de e-mail
    if (!email || !/\S+@\S+\.\S+/.test(email)) {
        message.textContent = 'Informe um e-mail válido.';
        message.style.color = 'red';
        return;
    }

    message.textContent = 'Enviando...';
    message.style.color = 'navy';
    submitBtn.disabled = true; // Desabilita para evitar clique duplo

    try {
        const response = await fetch('/enviar_email_recuperar_senha', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });

        const data = await response.json();

        // Mostra a mensagem genérica independente de sucesso/falha
        if (response.ok && data.success) {
            message.textContent = 'Se o e-mail existir, você receberá as instruções.';
            message.style.color = 'green';
        } else {
            message.textContent = 'Não foi possível processar sua solicitação agora.';
            message.style.color = 'red';
        }

    } catch (error) {
        console.error('Erro:', error);
        message.textContent = 'Erro ao conectar com o servidor.';
        message.style.color = 'red';
    } finally {
        submitBtn.disabled = false; // Reativa o botão
    }
});
