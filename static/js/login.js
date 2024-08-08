// Adiciona um ouvinte de eventos ao formulário de login para interceptar o evento de envio
// e processar os dados do formulário de forma assíncrona usando AJAX
document.getElementById('login-form').addEventListener('submit', function(event) {
    event.preventDefault(); // Impede o envio padrão do formulário para evitar o recarregamento da página
    
    // Exibe o indicador de carregamento para informar ao usuário que a solicitação está em andamento
    document.getElementById('loading-spinner').style.display = 'block';

    // Cria um objeto FormData com os dados do formulário
    var formData = new FormData(this);

    // Cria uma solicitação AJAX para enviar os dados do formulário ao servidor
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/');
    xhr.onload = function() {
        if (xhr.status === 200) {
            // Se a resposta é bem-sucedida, analisa a resposta JSON do servidor
            var response = JSON.parse(xhr.responseText);
            if (response.error) {
                // Oculta o indicador de carregamento após o recebimento da resposta
                document.getElementById('loading-spinner').style.display = 'none';
                // Se houver um erro na resposta, exibe a mensagem de erro e limpa o campo de senha
                console.log('Erro detectado:', response.error);
                document.getElementById('error-message').textContent = response.error;
                document.getElementById('error-message').classList.add('visible');
                document.getElementById('password').value = '';
            } else {
                // Se o login for bem-sucedido, salva as credenciais (se aplicável) e redireciona para o painel
                salvarCredenciais();
                window.location.href = '/painel';
            }
        } else {
            // Em caso de falha na solicitação AJAX, exibe uma mensagem de erro genérica
            console.error('Erro na solicitação AJAX:', xhr.status, xhr.statusText);
            document.getElementById('error-message').textContent = 'Falha na conexão. Tente novamente.';
            document.getElementById('error-message').classList.add('visible');
        }
    };
    xhr.onerror = function() {
        // Oculta o indicador de carregamento em caso de erro de rede ou CORS
        document.getElementById('loading-spinner').style.display = 'none';
        console.error('Erro de rede ou CORS.');
        document.getElementById('error-message').textContent = 'Problema de rede. Verifique sua conexão.';
        document.getElementById('error-message').classList.add('visible');
    };
    // Envia a solicitação com os dados do formulário
    xhr.send(formData);
});

// Adiciona um evento de escuta nos campos de entrada (email e password)
document.getElementById('email').addEventListener('input', function() {
    document.getElementById('error-message').classList.remove('visible');
});

// Adiciona um ouvinte de eventos para detectar mudanças no campo de senha
document.getElementById('password').addEventListener('input', function() {
    // Remove a classe 'visible' do elemento de mensagem de erro, ocultando-o
    document.getElementById('error-message').classList.remove('visible');
});

// Salva email e senha se o login for bem sucedido, pois e chamado dentro da outra funça apos logar
function salvarCredenciais() {
    const email = document.getElementById('email').value;
    const senha = document.getElementById('password').value;
    const lembrarMe = document.getElementById('remember').checked;
  
    if (lembrarMe) {
        // Salva o email e a senha no localStorage
        localStorage.setItem('email', email);
        localStorage.setItem('senha', senha);
    } else {
        // Remove as credenciais do localStorage
        localStorage.removeItem('email');
        localStorage.removeItem('senha');
    }
}
  
// Função para preencher os campos automaticamente (opcional)
function preencherCampos() {
    const emailSalvo = localStorage.getItem('email');
    const senhaSalva = localStorage.getItem('senha');

    if (emailSalvo && senhaSalva) {
        document.getElementById('email').value = emailSalvo;
        document.getElementById('password').value = senhaSalva;
        document.getElementById('remember').checked = true;
    }
}

// Chamar a função para preencher os campos ao carregar a página
window.onload = preencherCampos;
