// Obtém a referência ao formulário de redefinição de senha pelo seu ID
const form = document.getElementById('redefinir-senha-form');

// Obtém a referência ao elemento de mensagem pelo seu ID
const message = document.getElementById('message');

// Adiciona um ouvinte de evento ao formulário para capturar o evento de envio (submit)
form.addEventListener('submit', (event) => {
    // Impede o comportamento padrão do formulário de enviar dados e recarregar a página
    event.preventDefault();

    // Obtém o valor do campo "nova-senha" e "repetir-senha"
    const novaSenha = document.getElementById('nova-senha').value;
    const repetirSenha = document.getElementById('repetir-senha').value;

    // Verifica se as senhas coincidem
    if (novaSenha !== repetirSenha) {
        // Exibe uma mensagem de erro se as senhas não coincidirem
        message.textContent = 'As senhas não coincidem. Por favor, tente novamente.';
        message.style.color = 'red'; // Opcional: Adiciona um estilo para a mensagem de erro
        return; // Interrompe a execução do código
    }

    // Obtém os parâmetros da URL, incluindo o token
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token'); // Obtém o valor do parâmetro "token" da URL

    // Faz uma requisição POST para o servidor para redefinir a senha
    fetch('/nova_senha', {
        method: 'POST', // Método HTTP
        headers: { 'Content-Type': 'application/json' }, // Define o tipo de conteúdo como JSON
        body: JSON.stringify({ token, novaSenha }) // Converte os dados para uma string JSON e os envia no corpo da requisição
    })
    .then(response => response.json()) // Converte a resposta para JSON
    .then(data => {
        // Exibe a mensagem de resposta do servidor
        message.textContent = data.message;
        message.style.color = data.success ? 'green' : 'red'; // Estilo para a mensagem de sucesso ou erro
        if (data.success) {
            // Redireciona o usuário para a página de login em caso de sucesso
            window.location.href = '/';
        }
    })
    .catch(error => {
        // Lida com erros na requisição
        console.error('Erro:', error);
        message.textContent = 'Ocorreu um erro. Por favor, tente novamente mais tarde.';
        message.style.color = 'red'; // Opcional: Adiciona um estilo para a mensagem de erro
    });
});
