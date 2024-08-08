const form = document.querySelector('form');
const emailInput = document.getElementById('email');
const message = document.getElementById('message');

form.addEventListener('submit', (event) => {
    event.preventDefault(); // Impede o envio padrão do formulário

    // Exibe "Enviando..." enquanto a requisição está em andamento
    message.textContent = 'Enviando...';
    message.style.color = 'navy'; // Opcional: Muda a cor do texto para um estilo neutro durante o envio

    const email = emailInput.value;

    // Faz a requisição para o servidor
    fetch('/enviar_email_recuperar_senha', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: email })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Erro na resposta do servidor');
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            message.textContent = 'Um email de recuperação foi enviado.';
            message.style.color = 'green'; // Estilo para a mensagem de sucesso
        } else {
            message.textContent = 'Houve um problema ao enviar o email. Tente novamente.';
            message.style.color = 'red'; // Estilo para a mensagem de erro
        }
    })
    .catch(error => {
        console.error('Erro:', error);
        message.textContent = 'Email não cadastrado!';
        message.style.color = 'red'; // Estilo para a mensagem de erro
    });
});
