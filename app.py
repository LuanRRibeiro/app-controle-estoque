'''Aplicativo WEB - Projeto Integrado I'''

from flask import Flask, request, redirect, render_template, session, url_for, jsonify
import os
from werkzeug.utils import secure_filename
import psycopg2
from google.cloud import storage
import datetime


app = Flask(__name__)

app.secret_key = 'sua_chave_secreta_aqui'

carrinho_compras = []

# Função que faz conexao do banco de dados
def conexao_bd():
    host = "dpg-cof9fjq1hbls7399en5g-a.oregon-postgres.render.com"
    database = "bd_app_estoque"
    user = "bd_app_estoque_user"
    password = "D31cgvSdlSNBr5SnLiaaismYUTKv2Ct7"

    try:
        conexao = psycopg2.connect(host=host, database=database, user=user, password=password)
        return conexao
    except psycopg2.Error as e:
      print("Falha ao conectar ao banco de dados:", e)
      return None

# Função para verificar se o usuário está autenticado
def esta_autenticado():
    return 'username' in session

# Rota para a página de login
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        banco = conexao_bd()
        cursor = banco.cursor()

        sql = 'SELECT id, usuario, senha FROM usuario WHERE usuario = %s AND senha = %s'

        cursor.execute(sql, (username, password,))
        usuario = cursor.fetchone()
        

        # Se localizar Usuario e Senha Abre o Painel
        if usuario is not None:
            login = usuario[1]
            senha = usuario[2]
            
            cursor.close()
            banco.close()
        
            # Definir a sessão do usuário se as credenciais estiverem corretas
            session['username'] = username
            return redirect('/painel')
        else:
            return redirect('/erro')
        
    return render_template('login.html')

# Rota para usuario não localizado
@app.route('/erro')
def erro():
    return render_template('login_erro.html')

# Rota para fazer logout
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# Rota para usuario localizado
@app.route('/painel')
def painel():
    if not esta_autenticado():
        return redirect(url_for('login'))
    
    
    if carrinho_compras == []:
        # Essa busca produto, busca no banco de dados e carrega a lista na pagina
        quantidade_itens_carrinho = 0
    else:
        # Atualiza a quantidade total de itens no carrinho
        quantidade_itens_carrinho = calcular_quantidade_total_carrinho(carrinho_compras)
        
    
    # Renderiza o template 'painel.html' passando a lista de produtos e a quantidade de itens no carrinho
    return render_template('painel.html', produtos='', quantidade_itens_carrinho=quantidade_itens_carrinho)

# Buscar_produto no banco de dados
@app.route('/buscar_produtos', methods=['POST'])
def buscar_produtos():
    termo = request.json['termo'].lower()

    # Verifica se o termo está vazio
    if not termo:
        # Retorna uma lista vazia se o termo estiver vazio
        return jsonify([])

    banco = conexao_bd()
    cursor = banco.cursor()

    # Verificar se o termo é um número
    if termo.isdigit():
        # Se for número, busca pelo ID
        cursor.execute("SELECT * FROM produtos WHERE CAST(quantidade AS integer) >= 1 AND id = %s", (termo,))
    else:
        # Se for uma string, busca pelo nome ou descrição
        cursor.execute("SELECT * FROM produtos WHERE CAST(quantidade AS integer) >= 1 AND (LOWER(nome) LIKE %s OR LOWER(descricao) LIKE %s)", ('%' + termo + '%', '%' + termo + '%'))


    produtos = cursor.fetchall()
    
    cursor.close()
    banco.close()
    
    # Converta os resultados em uma lista de dicionários para jsonify
    produtos_json = []
    for produto in produtos:
        produto_dict = {
            'id': produto[0],
            'nome': produto[1],
            'quantidade': int(produto[2]),
            'descricao': produto[3],
            'preco_compra': produto[4],
            'preco_venda': float(produto[5]),
            'lucro_reais': produto[6],
            'lucro_porcentagem': produto[7],
            'imagem': produto[8]
        }

        # Retorna os produtos encontrados como JSON
        produtos_json.append(produto_dict)
    return jsonify(produtos_json)

# Função que acessa pagina do carrinho
@app.route('/carrinho')
def carrinho():
    if not esta_autenticado():
        return redirect(url_for('login'))
    # Acessando pagina do carrinho de compras

    return render_template('carrinho.html', carrinho_compras=carrinho_compras)

# Função que adiciona produto no carrinho
@app.route('/adicionar_carrinho', methods=['POST'])
def adicionar_carrinho():
    produto = request.json
    
    # Verificar se o produto já está no carrinho
    for item in carrinho_compras:
        if item['id'] == produto['id']:
            # Se o produto já está no carrinho, apenas atualiza a quantidade
            item['quantidade'] += produto['quantidade']
            item['estoque'] -= produto['quantidade']
            break
    else:
        # Se o produto não está no carrinho, adiciona ele ao carrinho
        carrinho_compras.append(produto)
    
    # Reduzir a quantidade do produto no banco de dados
    diminuir_quantidade_produto_no_bd(produto['id'], produto['quantidade'])
    
    quantidade_itens_carrinho = calcular_quantidade_total_carrinho(carrinho_compras)

    return jsonify({'message': 'Produto adicionado ao carrinho com sucesso', 'quantidadeItens': quantidade_itens_carrinho})


# Função que remove item do carrinho
@app.route('/remover_do_carrinho', methods=['POST'])
def remover_produto_do_carrinho():
    # Recebe os dados JSON enviados pela solicitação POST
    dados_produto = request.json

    # Obtém o ID do produto a ser removido
    produto_id = dados_produto.get('id')
    
    # Remove o produto do carrinho de compras
    for produto in carrinho_compras:
        if int(produto['id']) == int(produto_id):
            carrinho_compras.remove(produto)
            # Reduzir a quantidade do produto no banco de dados
            aumentar_quantidade_produto_no_bd(produto['id'], produto['quantidade'])
            break
    # Retorna uma resposta indicando sucesso
    return jsonify({'message': 'Produto removido com sucesso'}), 200

# Função para adicionar quantidade ao estoque do produto no banco de dados
def aumentar_quantidade_produto_no_bd(id_produto, quantidade):
    # Aqui você implementa a lógica para aumentar a quantidade do produto no banco de dados
    # Exemplo:
    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute("UPDATE produtos SET quantidade = quantidade + %s WHERE id = %s", (quantidade, id_produto))
    banco.commit()
    cursor.close()
    banco.close()

# Função para diminuir quantidade do estoque do produto no banco de dados
def diminuir_quantidade_produto_no_bd(id_produto, quantidade):
    # Aqui você implementa a lógica para diminuir a quantidade do produto no banco de dados
    # Exemplo:
    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute("UPDATE produtos SET quantidade = quantidade - %s WHERE id = %s", (quantidade, id_produto))
    banco.commit()
    cursor.close()
    banco.close()

# Função que calcula a quantide de itens no carrinho
def calcular_quantidade_total_carrinho(carrinho_compras):
    qtd_intens_carrinho = 0
    for item in carrinho_compras:
        quantidade = item['quantidade']
        qtd_intens_carrinho += quantidade
    
    return qtd_intens_carrinho

# Função que atualiza quantidade de produto em estoque conforme aumento ou diminui no carrinho
@app.route('/atualizar_estoque', methods=['POST'])
def atualizar_estoque():
    produto = request.json
    
    produto_id = produto['id']
    nova_quantidade = produto['quantidade']
    estoque = produto['estoque']
    acao = produto['acao']
    
    
    for item in carrinho_compras:
        if item['id'] == produto_id:
            item['estoque'] = estoque
            item['quantidade'] = nova_quantidade
            item['valorTotal'] = nova_quantidade * item['preco']  # Atualiza o valor total também se necessário
            break  # Encerra o loop após encontrar o produto
    
    # Se clicar no btn aumentar diminui a quantidade no bd
    if acao == 'btn_aumentar':
        diminuir_quantidade_produto_no_bd(produto['id'], 1)
    else:
        aumentar_quantidade_produto_no_bd(produto['id'], 1)
                

    return 'Estoque atualizado com sucesso.', 200

# Rota para pagina de cadastrar produtos caso usuario esteja autenticado.
@app.route('/cadastro_produtos')
def cadastro_de_produtos():
    if not esta_autenticado():
        return redirect(url_for('login'))
    return render_template('cadastro_produtos.html')

# Rota para cadastrar produto.
@app.route('/adicionar_produto', methods=['POST'])
def pagina_adicionar_produto():
    # Recupere os dados do formulário enviado pelo JavaScript
    nome = request.form['nome'].upper()
    quantidade = int(request.form['quantidade'])
    descricao = request.form['descricao'].upper()
    preco_compra = request.form['preco_compra']
    preco_venda = request.form['preco_venda']
    lucro_reais = request.form['lucro_reais']
    lucro_porcentagem = request.form['lucro_porcentagem']
    lucro_porcentagem = float(lucro_porcentagem.rstrip('%'))
    
    # Verifique se um arquivo de imagem foi enviado
    if 'imagem' in request.files:
        imagem = request.files['imagem']
        enviado = 'sim'
    else:
        enviado = 'nao'
    
    if produto_existe(nome):
        return 'Produto já cadastrado anteriormente!', 409
    else:
        if enviado == 'sim':
            # Obtém pasta raiz do aplicativo
            pasta_raiz = os.path.dirname(os.path.realpath(__file__))
            
            pasta_temp_heroku = '/tmp/temp'

            # Obtém a extensão do arquivo
            extensao = imagem.filename.split('.')[-1]

            # Obtém o nome do arquivo com extensão
            arquivo = secure_filename(nome + '.' + extensao)
           
            # Verifica se o diretório temporário existe e, se não, cria-o
            if not os.path.exists(pasta_temp_heroku):
                os.makedirs(pasta_temp_heroku)
            
            
            caminho_completo = os.path.join(pasta_temp_heroku, arquivo)
            imagem.save(os.path.join(pasta_temp_heroku, arquivo))

            # Nome do arquivo de chave de serviço
            chave = 'projetoteste-398517-9de2939260b4.json'

            # Caminho completo para o arquivo de chave de serviço
            caminho_arquivo_json = pasta_raiz + '/' + chave

            # Define as credenciais de autenticação para o Google Cloud Storage
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = caminho_arquivo_json

            nome_bucket = "bd_imagens"
            caminho_imagem_local = caminho_completo
            nome_blob_destino = arquivo
            
            fazer_upload_imagem_gcs(nome_bucket, caminho_imagem_local, nome_blob_destino)
            url = obter_url_imagem(nome_bucket, nome_blob_destino)

            # Exclui o diretório temporário e seu conteúdo
            os.remove(caminho_completo)
            
            # Chame a função desejada com os dados recebidos
            resultado = adicionar_produto(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, url)

            # Retorne uma resposta adequada para o JavaScript
            if resultado == 'Cadastrado':
                return 'Produto cadastrado com sucesso!', 200
            else:
                return 'Ocorreu um erro ao cadastrar o produto. Por favor, tente novamente.', 500
        else:
            url = ''
            # Chame a função desejada com os dados recebidos
            resultado = adicionar_produto(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, url)
            return 'Produto cadastrado com sucesso!', 200

def fazer_upload_imagem_gcs(nome_bucket, caminho_imagem_local, nome_blob_destino):
    # Inicializa o cliente do Google Cloud Storage
    cliente_storage = storage.Client()

    # Obtém o bucket
    bucket = cliente_storage.bucket(nome_bucket)

    # Cria um novo blob e faz upload da imagem
    blob = bucket.blob(nome_blob_destino)
    blob.upload_from_filename(caminho_imagem_local)

def obter_url_imagem(nome_bucket, nome_blob):
    # Inicializa o cliente do Google Cloud Storage
    cliente_storage = storage.Client()

    # Obtém o bucket
    bucket = cliente_storage.bucket(nome_bucket)

    # Obtém o blob
    blob = bucket.blob(nome_blob)

    # Gera a URL assinada com uma expiração longa
    url = blob.generate_signed_url(expiration=datetime.timedelta(days=3652))

    return url

# função que analisa se o produto ja esta cadastrado.
def produto_existe(nome_produto):
    banco = conexao_bd()
    cursor = banco.cursor()

    cursor.execute("SELECT * FROM produtos WHERE nome = %s", (nome_produto,))
    produto = cursor.fetchone()

    # Fechar o cursor e a conexão
    cursor.close()
    banco.close()

    return produto is not None

# função que cadastra o produto.
def adicionar_produto(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem):
    
    if produto_existe(nome):
        return 'Existe'
    else:
        banco = conexao_bd()
        cursor = banco.cursor()

        # Comandos SQL para inserir produtos
        sql = "INSERT INTO produtos (nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        dados_produto = (nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem)

        # Executar o comando SQL
        cursor.execute(sql, dados_produto)

        # Commit para salvar as alterações no banco de dados
        banco.commit()

        # Fechar o cursor e a conexão
        cursor.close()
        banco.close()
        return 'Cadastrado'      

# Função para formatar o valor do preço
def formatar_valor(valor):
    return f'{valor:.2f}'

# Função para acessar pagina de estoque
@app.route('/estoque', methods=['GET'])
def pagina_estoque():
    if not esta_autenticado():
        return redirect(url_for('login'))
    
    texto = 'Buscar Produtos - Em Estoque!'

    produtos = []

    banco = conexao_bd()
    cursor = banco.cursor()
    
    cursor.execute("SELECT * FROM produtos WHERE quantidade >= 1")
    produtos_bd = cursor.fetchall()

    if produtos_bd != []:
        for produto in produtos_bd:
            id = produto[0]
            nome = produto[1]
            quantidade = int(produto[2])
            descricao = produto[3]
            preco_compra = produto[4]
            preco_venda = float(produto[5])
            lucro_reais = produto[6]
            lucro_porcentagem = produto[7]
            imagem = produto[8]
            produtos.append({'nome': nome, 'descricao': descricao, 'quantidade': quantidade, 'preco': preco_venda})
    
        # Formatando os valores de preço antes de passá-los para o template
        for produto in produtos:
            produto['preco_formatado'] = formatar_valor(produto['preco'])
    return render_template('pagina_estoque.html', produtos=produtos, texto_h1=texto)

# Função para acessar pagina de produtos que não tem no estoque
@app.route('/fora_estoque', methods=['GET'])
def pagina_fora_estoque():
    if not esta_autenticado():
        return redirect(url_for('login'))
    
    texto = 'Buscar Produtos - Fora de Estoque!'

    produtos = []

    banco = conexao_bd()
    cursor = banco.cursor()
    
    cursor.execute("SELECT * FROM produtos WHERE quantidade = 0")
    produtos_banco_dados_zerados = cursor.fetchall()
        
    if produtos_banco_dados_zerados != []:
        for produto in produtos_banco_dados_zerados:
            id = produto[0]
            nome = produto[1]
            quantidade = int(produto[2])
            descricao = produto[3]
            preco_compra = produto[4]
            preco_venda = float(produto[5])
            lucro_reais = produto[6]
            lucro_porcentagem = produto[7]
            imagem = produto[8]
            produtos.append({'nome': nome, 'descricao': descricao, 'quantidade': quantidade, 'preco': preco_venda})
    
        # Formatando os valores de preço antes de passá-los para o template
        for produto in produtos:
            produto['preco_formatado'] = formatar_valor(produto['preco'])
    return render_template('pagina_estoque.html', produtos=produtos, texto_h1=texto)

@app.route('/pagina_pagamento', methods=['GET', 'POST'])
def pagina_pagamento():
    total = None
    if request.method == 'POST':
        data = request.json
        total = data.get('total')
    return render_template('pagamento.html', total=total)

@app.route('/finalizar_pagamento', methods=['GET', 'POST'])
def finalizar_pagamento():
    banco = conexao_bd()
    cursor = banco.cursor()

    if request.method == 'POST':
        for produto in carrinho_compras:
            id_produto = produto['id']
            quantidade_comprada = produto['quantidade']
            cursor.execute("UPDATE produtos SET quantidade = quantidade - %s WHERE id = %s", (quantidade_comprada, id_produto))
            banco.commit()
        carrinho_compras.clear()

    mensagem = "Pagamento finalizado com sucesso!"
    return render_template('pedido_finalizado.html', mensagem=mensagem)
    

if __name__ == '__main__':
    app.run()
    #app.run(debug=True)
    #app.run(host='0.0.0.0')

 