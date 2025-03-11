'''Aplicativo WEB - Projeto Integrado I'''

from flask import Flask, request, redirect, render_template, session, url_for, jsonify
from werkzeug.utils import secure_filename
import psycopg2
import datetime
from flask import Flask, request, redirect, url_for, flash
from flask_mail import Mail, Message
from flask import Flask, request, jsonify
import smtplib
from email.message import EmailMessage
import uuid
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from google.cloud import storage
from google.oauth2 import service_account
import os
import re
from urllib.parse import urlsplit
from psycopg2.extras import RealDictCursor
from decimal import Decimal




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

# Função para logar no app verificando login e senha
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            return jsonify({'error': 'Email e senha são obrigatórios'})

        banco = conexao_bd()
        cursor = banco.cursor()

        # Busca o hash da senha armazenado no banco de dados
        sql = 'SELECT id_usuario, senha FROM vendedores WHERE email = %s'
        cursor.execute(sql, (email,))
        usuario = cursor.fetchone()

        

        cursor.close()
        banco.close()

        if usuario:
            id_usuario, senha_hash = usuario

            # Verifica se a senha fornecida corresponde ao hash armazenado
            if check_password_hash(senha_hash, password):
                # Contabilizando acesso de cada usuário  
                banco = conexao_bd()
                cursor = banco.cursor()
                cursor.execute('UPDATE vendedores SET acesso = acesso + 1 WHERE id_usuario = %s', (id_usuario,))
                banco.commit()
                cursor.close()
                banco.close()
                
                # Define a sessão do usuário se as credenciais estiverem corretas
                session['username'] = email
                return jsonify({'error': None})
            else:
                error = 'Nome de usuário ou senha inválido(a)'
        else:
            error = 'Nome de usuário ou senha inválido(a)'

        return jsonify({'error': error})

    return render_template('login.html', error=None)

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
    
    carrinho_compras.clear()

    email = session.get('username')
    
    # Verifica os itens no carrinho do usuário
    sql_verificar = '''
        SELECT produto_id, quantidade 
        FROM itens_no_carrinho 
        WHERE usuario_id = (SELECT id_usuario FROM vendedores WHERE email = %s)
    '''

    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute(sql_verificar, (email,))
    resultado = cursor.fetchall()
    
    for item in resultado:
        produto_id = item[0]
        quantidade_selecionada = item[1]

        sql_verificar_produto = '''
        SELECT nome, descricao, quantidade, preco_venda
        FROM produtos 
        WHERE id = %s'''

        cursor.execute(sql_verificar_produto, (produto_id,))
        resultado_produto = cursor.fetchone()
        
        nome = resultado_produto[0]
        descricao = resultado_produto[1]
        estoque = resultado_produto[2]
        preco = float(resultado_produto[3])

        valor_total = float(preco * quantidade_selecionada)

        carrinho_compras.append({'id': produto_id, 'nome': nome, 'descricao': descricao, 'estoque': estoque, 'quantidade': quantidade_selecionada, 'preco': preco, 'valorTotal': valor_total})


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

# Função que acessa a página do carrinho
@app.route('/carrinho')
def carrinho():
    if not esta_autenticado():
        return redirect(url_for('login'))

    # Acessando página do carrinho de compras
    carrinho_compras.clear()

    email = session.get('username')

    banco = conexao_bd()
    cursor = banco.cursor()
    
    # Verificar o usuário e obter o id_usuario
    sql_verificar_usuario = '''
        SELECT id_usuario 
        FROM vendedores 
        WHERE email = %s
    '''
    cursor.execute(sql_verificar_usuario, (email,))
    resultado_usuario = cursor.fetchone()

    if resultado_usuario:
        id_usuario = resultado_usuario[0]

        # Verifica os itens no carrinho do usuário
        sql_verificar_carrinho = '''
            SELECT produto_id, quantidade 
            FROM itens_no_carrinho 
            WHERE usuario_id = %s
        '''
        cursor.execute(sql_verificar_carrinho, (id_usuario,))
        resultado_carrinho = cursor.fetchall()
        
        for item in resultado_carrinho:
            produto_id = item[0]
            quantidade_selecionada = item[1]

            sql_verificar_produto = '''
                SELECT nome, descricao, quantidade, preco_venda, caminho_imagem
                FROM produtos 
                WHERE id = %s
            '''
            cursor.execute(sql_verificar_produto, (produto_id,))
            resultado_produto = cursor.fetchone()
            nome = resultado_produto[0]
            descricao = resultado_produto[1]
            estoque = resultado_produto[2]
            preco = float(resultado_produto[3])
            imagem = resultado_produto[4]

            valor_total = float(preco * quantidade_selecionada)

            carrinho_compras.append({
                'id': produto_id,
                'nome': nome,
                'descricao': descricao,
                'estoque': estoque,
                'quantidade': quantidade_selecionada,
                'preco': preco,
                'valorTotal': valor_total,
                'imagem': imagem
            })
    else:
        # Se o usuário não for encontrado
        return redirect(url_for('login'))
    
    cursor.close()
    banco.close()

    return render_template('carrinho.html', carrinho_compras=carrinho_compras)

# Função que adiciona produto no carrinho
@app.route('/adicionar_carrinho', methods=['POST'])
def adicionar_carrinho():
    if not esta_autenticado():
        return redirect(url_for('login'))
    
    email = session.get('username')
    
    produto = request.json
    produto_id = produto['id']
    quantidade = produto['quantidade']
    preco_unitario = produto['preco']

    banco = conexao_bd()
    cursor = banco.cursor()
    
    # Verificar o usuário e obter o id_usuario
    sql_verificar = '''
        SELECT id_usuario 
        FROM vendedores 
        WHERE email = %s
    '''
    cursor.execute(sql_verificar, (email,))
    resultado = cursor.fetchone()

    if resultado:
        id_usuario = resultado[0]

        # Verifica se o item já está no carrinho do usuário
        sql_verificar_carrinho = '''
            SELECT COUNT(*) 
            FROM itens_no_carrinho 
            WHERE usuario_id = %s AND produto_id = %s
        '''
        cursor.execute(sql_verificar_carrinho, (id_usuario, produto_id))
        resultado_carrinho = cursor.fetchone()
        quantidade_produto_no_carrinho = resultado_carrinho[0]

        if quantidade_produto_no_carrinho > 0:
            # Se o item já estiver no carrinho, atualiza a quantidade
            sql_update = '''
                UPDATE itens_no_carrinho 
                SET quantidade = quantidade + %s
                WHERE usuario_id = %s AND produto_id = %s
            '''
            cursor.execute(sql_update, (quantidade, id_usuario, produto_id))
        else:
            # Se o item não estiver no carrinho, insere um novo registro
            sql_insert = '''
                INSERT INTO itens_no_carrinho (usuario_id, produto_id, quantidade, preco_unitario)
                VALUES (%s, %s, %s, %s)
            '''
            cursor.execute(sql_insert, (id_usuario, produto_id, quantidade, preco_unitario))

        banco.commit()
        cursor.close()
        banco.close()

        # Reduzir a quantidade do produto no banco de dados
        diminuir_quantidade_produto_no_bd(produto['id'], produto['quantidade'], 'adicionar')
        
        quantidade_itens_carrinho = calcular_quantidade_total_carrinho(carrinho_compras)

        return jsonify({'message': 'Produto adicionado ao carrinho com sucesso', 'quantidadeItens': quantidade_itens_carrinho})
    else:
        cursor.close()
        banco.close()
        return jsonify({'error': 'Usuário não encontrado'}), 404

# Função que remove item do carrinho
@app.route('/remover_do_carrinho', methods=['POST'])
def remover_produto_do_carrinho():
    # Recebe os dados JSON enviados pela solicitação POST
    dados_produto = request.json

    
    # Obtém o ID do produto a ser removido
    produto_id = int(dados_produto.get('id'))


    banco = conexao_bd()
    cursor = banco.cursor()

    sql_consultar = '''
        SELECT quantidade
        FROM itens_no_carrinho 
        WHERE produto_id = %s'''

    cursor.execute(sql_consultar, (produto_id,))
    resultado = cursor.fetchone()
    quantidade = resultado[0]

    sql_remover = '''
        DELETE FROM itens_no_carrinho 
        WHERE produto_id = %s
        '''
    
    cursor.execute(sql_remover, (produto_id,))
    banco.commit()

    cursor.close()
    banco.close()
    
    aumentar_quantidade_produto_no_bd(produto_id, quantidade)
          
    # Retorna uma resposta indicando sucesso
    return jsonify({'message': 'Produto removido com sucesso'}), 200

# Função para adicionar quantidade ao estoque do produto no banco de dados
def aumentar_quantidade_produto_no_bd(id_produto, quantidade):
    # Aqui você implementa a lógica para aumentar a quantidade do produto no banco de dados
    banco = conexao_bd()
    cursor = banco.cursor()

    cursor.execute("UPDATE produtos SET quantidade = quantidade + %s WHERE id = %s", (quantidade, id_produto))

        
    sql_atualizar = '''
    UPDATE itens_no_carrinho 
    SET quantidade = quantidade - %s
    WHERE produto_id = %s'''

    cursor.execute(sql_atualizar, (quantidade, int(id_produto)))


    banco.commit()
    cursor.close()
    banco.close()

# Função para diminuir quantidade do estoque do produto no banco de dados
def diminuir_quantidade_produto_no_bd(id_produto, quantidade, tipo):
    # Aqui você implementa a lógica para diminuir a quantidade do produto no banco de dados
    
    banco = conexao_bd()
    cursor = banco.cursor()

    cursor.execute("UPDATE produtos SET quantidade = quantidade - %s WHERE id = %s", (quantidade, id_produto))

    if tipo == 'btn_aumentar':
        sql_atualizar = '''
        UPDATE itens_no_carrinho 
        SET quantidade = quantidade + %s
        WHERE produto_id = %s'''

        cursor.execute(sql_atualizar, (quantidade, int(id_produto)))


    banco.commit()
    cursor.close()
    banco.close()

# Função que calcula a quantide de itens no carrinho
def calcular_quantidade_total_carrinho(carrinho_compras):
    qtd_intens_carrinho = 0
    
    sql_verificar = '''
        SELECT SUM(quantidade) AS total_quantidade 
        FROM itens_no_carrinho 
    '''
    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute(sql_verificar,)
    total_quantidade = cursor.fetchone()[0]

    cursor.close()
    banco.close()

    return total_quantidade
    
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
        diminuir_quantidade_produto_no_bd(produto['id'], 1, 'btn_aumentar')
    else:
        aumentar_quantidade_produto_no_bd(produto['id'], 1)
                

    return 'Estoque atualizado com sucesso.', 200

# Rota para pagina de cadastrar produtos caso usuario esteja autenticado.
@app.route('/cadastro_produtos')
def cadastro_de_produtos():
    if not esta_autenticado():
        return redirect(url_for('login'))
    return render_template('produtos/cadastro_produtos.html')

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
            
            pasta_temp = '/tmp/temp'

            # Obtém a extensão do arquivo
            extensao = imagem.filename.split('.')[-1]

            # Obtém o nome do arquivo com extensão
            arquivo = secure_filename(nome + '.' + extensao)
           
            # Verifica se o diretório temporário existe e, se não, cria-o
            if not os.path.exists(pasta_temp):
                os.makedirs(pasta_temp)
                        
            caminho_completo = os.path.join(pasta_temp, arquivo)
            imagem.save(os.path.join(pasta_temp, arquivo))

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
            url = 'https://storage.cloud.google.com/bd_imagens/sem_imagem.png'
            # Chame a função desejada com os dados recebidos
            resultado = adicionar_produto(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, url)
            return 'Produto cadastrado com sucesso!', 200

# Fazer Upload da imagem do produto
def fazer_upload_imagem_gcs(nome_bucket, caminho_imagem_local, nome_blob_destino):
    # Inicializa o cliente do Google Cloud Storage
    cliente_storage = storage.Client()

    # Obtém o bucket
    bucket = cliente_storage.bucket(nome_bucket)

    # Cria um novo blob e faz upload da imagem
    blob = bucket.blob(nome_blob_destino)
    blob.upload_from_filename(caminho_imagem_local)

# Obter a Url da imagem
def obter_url_imagem(nome_bucket, nome_blob):
    # Inicializa o cliente do Google Cloud Storage
    cliente_storage = storage.Client()

    # Obtém o bucket
    bucket = cliente_storage.bucket(nome_bucket)

    # Obtém o blob
    blob = bucket.blob(nome_blob)

    # Gera a URL assinada com uma expiração longa
    url = blob.generate_signed_url(expiration=timedelta(days=3652))

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

# Rota para editar produto.
# Ao clicar no Botao Editar chama esta função
@app.route('/editar-produto/<int:id>', methods=['GET', 'POST'])
def editar_produto(id):
    banco = conexao_bd()
    cursor = banco.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('SELECT * FROM produtos WHERE id = %s', (id,))
    produto = cursor.fetchone()
    cursor.close()
    banco.close()

    if produto is None:
        return "Produto não encontrado!", 404

    # Exibi a pagina para editar produto
    return render_template('editar_produto.html', produto=produto)

# Rota salvar no BD produto editado.
@app.route('/salvar_produto_editado/<int:id_produto>', methods=['POST'])
def salvar_produto_editado(id_produto):

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

    # Conectando no Banco de Dados
    banco = conexao_bd()
    cursor = banco.cursor()

    # Primeiro, obtenha nome e a URL da imagem do produto antes de excluí-lo
    cursor.execute("SELECT nome, caminho_imagem FROM produtos WHERE id = %s", (id_produto,))
    produto = cursor.fetchone()

    nome_produto = produto[0]
    imagem_url = produto[1]

    if enviado == 'sim':
        if produto:
            if nome_produto != nome:
                # Se a URL da imagem existir, exclua a imagem do GCS
                if imagem_url:
                    # Chamando a função para excluir a imagem para que possamos inserir a outra com novo nome
                    excluir_imagem_gcs(imagem_url)


            # Obtém pasta raiz do aplicativo
            pasta_raiz = os.path.dirname(os.path.realpath(__file__))
            
            pasta_temp = '/tmp/temp'

            # Obtém a extensão do arquivo
            extensao = imagem.filename.split('.')[-1]

            # Obtém o nome do arquivo com extensão
            arquivo = secure_filename(nome + '.' + extensao)
            
            # Verifica se o diretório temporário existe e, se não, cria-o
            if not os.path.exists(pasta_temp):
                os.makedirs(pasta_temp)
                        
            caminho_completo = os.path.join(pasta_temp, arquivo)
            imagem.save(os.path.join(pasta_temp, arquivo))

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
            
            # Chame a função desejada para salvar no BD com os dados recebidos
            resultado = editar_produto_banco_dados(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, url, id_produto)
            
            # Retorne uma resposta adequada para o JavaScript
            if resultado == 'Cadastrado':
                return 'Produto editado com sucesso!', 200
            else:
                return 'Ocorreu um erro ao editar o produto. Por favor, tente novamente.', 500
    else:
        if nome_produto != nome:
            # Se a URL da imagem existir, exclua a imagem do GCS
            if imagem_url:
                # Chamando a função para excluir a imagem para que possamos inserir a outra com novo nome
                excluir_imagem_gcs(imagem_url)

        url = 'https://storage.cloud.google.com/bd_imagens/sem_imagem.png'
        # Chame a função desejada com os dados recebidos
        resultado = editar_produto_banco_dados(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, url, id_produto)
        return 'Produto editado com sucesso!', 200

# função que cadastra o produto.
def editar_produto_banco_dados(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem, id_produto):
    banco = conexao_bd()
    cursor = banco.cursor()

    # Comandos SQL para inserir produtos
    sql = "UPDATE produtos SET nome = %s, quantidade = %s, descricao = %s, preco_compra = %s, preco_venda = %s, lucro_reais = %s, lucro_porcentagem = %s, caminho_imagem = %s WHERE id = %s"
    dados_produto = (nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem, id_produto)

    # Executar o comando SQL
    cursor.execute(sql, dados_produto)

    # Commit para salvar as alterações no banco de dados
    banco.commit()

    # Fechar o cursor e a conexão
    cursor.close()
    banco.close()
    return 'Cadastrado' 

@app.route('/listar_produtos')
def listar_produtos():
    search = request.args.get('search', '')
    fora_de_estoque = request.args.get('fora_de_estoque', '0') == '1'  # Desativado por padrão

    pagina = request.args.get('pagina', 1, type=int)
    itens_por_pagina = 10
    offset = (pagina - 1) * itens_por_pagina

    produtos = []
    banco = conexao_bd()
    cursor = banco.cursor()

    # Construindo a consulta principal
    sql = "SELECT * FROM produtos WHERE 1=1"  # Condição sempre verdadeira para permitir filtros dinâmicos
    params = []

    if fora_de_estoque:
        sql += " AND quantidade = 0"
    else:
        sql += " AND quantidade > 0"  # Padrão: exibir produtos em estoque

    if search:
        try:
            id_busca = int(search)
            sql += " AND id = %s"
            params.append(id_busca)
        except ValueError:
            sql += " AND nome ILIKE %s"
            params.append(f'%{search}%')

    # Contagem total de produtos para a paginação
    count_sql = "SELECT COUNT(*) FROM produtos WHERE 1=1"
    count_params = []

    if fora_de_estoque:
        count_sql += " AND quantidade = 0"
    else:
        count_sql += " AND quantidade > 0"

    if search:
        try:
            id_busca = int(search)
            count_sql += " AND id = %s"
            count_params.append(id_busca)
        except ValueError:
            count_sql += " AND nome ILIKE %s"
            count_params.append(f'%{search}%')

    cursor.execute(count_sql, count_params)
    total_produtos = cursor.fetchone()[0]
    total_paginas = (total_produtos // itens_por_pagina) + (1 if total_produtos % itens_por_pagina > 0 else 0)

    # Aplicando ordenação e paginação
    sql += " ORDER BY id LIMIT %s OFFSET %s"
    params.extend([itens_por_pagina, offset])

    cursor.execute(sql, params)
    produtos_bd = cursor.fetchall()

    for produto in produtos_bd:
        produtos.append({
            'id': produto[0],
            'nome': produto[1],
            'quantidade': produto[2],
            'descricao': produto[3],
            'preco_compra': produto[4],
            'preco_venda': produto[5],
            'lucro_reais': produto[6],
            'lucro_porcentagem': produto[7],
            'imagem_url': produto[8]
        })

    banco.close()

    return render_template(
        'listar_produtos.html',
        produtos=produtos,
        search_query=search,
        fora_de_estoque=fora_de_estoque,
        pagina=pagina,
        total_paginas=total_paginas
    )




@app.route('/excluir-produto/<int:id>', methods=['POST'])
def excluir_produto(id):
    banco = conexao_bd()
    cursor = banco.cursor()

    # Primeiro, obtenha a URL da imagem do produto antes de excluí-lo
    cursor.execute("SELECT caminho_imagem FROM produtos WHERE id = %s", (id,))
    produto = cursor.fetchone()

    if produto:
        imagem_url = produto[0]

        # Exclua o produto do banco de dados
        cursor.execute("DELETE FROM produtos WHERE id = %s", (id,))
        banco.commit()

        # Feche a conexão com o banco de dados
        cursor.close()
        banco.close()

        # Se a URL da imagem existir, exclua a imagem do GCS
        if imagem_url:
            excluir_imagem_gcs(imagem_url)

    return redirect(url_for('listar_produtos'))

def excluir_imagem_gcs(imagem_url):
    # Obtém o diretório raiz do script
    pasta_raiz = os.path.dirname(os.path.realpath(__file__))
    
    # Caminho para o arquivo de chave JSON
    caminho_chave = os.path.join(pasta_raiz, 'projetoteste-398517-9de2939260b4.json')

    # Carregar as credenciais a partir do arquivo
    credentials = service_account.Credentials.from_service_account_file(caminho_chave)
    
    # Configurar o cliente de storage
    storage_client = storage.Client(credentials=credentials)

    # Nome do bucket
    nome_bucket = 'bd_imagens'

    # Dividir a URL em partes
    parsed_url = urlsplit(imagem_url)
    path = parsed_url.path
    
    # Extrair o nome do arquivo do caminho, removendo o prefixo do bucket
    nome_blob = path.lstrip('/').replace(f'{nome_bucket}/', '', 1)
    
    if nome_blob:
        # Referenciar o bucket e o blob
        bucket = storage_client.bucket(nome_bucket)
        blob = bucket.blob(nome_blob)
        
        # Verificar a imagem cadastrada do produto não e sem_imagem.png utilizada para produtos sem fotos ao cadastrar
        if nome_blob != 'sem_imagem.png':
            try:
                # Excluir o blob
                blob.delete()
                #print(f"Imagem '{nome_blob}' excluída com sucesso do bucket '{nome_bucket}'.")
            except Exception as e:
                print(f"Erro ao excluir a imagem: {e}")
    else:
        print("URL de imagem inválida.")

# Função para acessar o metodo de pagamento
@app.route('/pagina_pagamento', methods=['GET'])
def pagina_pagamento():
    total = request.args.get('total', 0.00)
    return render_template('pagamento.html', total=float(total))

# Função para finalizar o pagamento com desconto proporcional
@app.route('/finalizar_pagamento', methods=['POST'])
def finalizar_pagamento():
    banco = conexao_bd()
    cursor = banco.cursor()

    try:
        desconto_total = float(request.form.get('desconto', 0))  # Obtém o desconto total da compra
        tipo_pagamento = request.form.get('tipo_pagamento', 'não informado')  # Obtém o tipo de pagamento
        
        # 1. Buscar os itens do carrinho
        cursor.execute("SELECT produto_id, quantidade FROM itens_no_carrinho;")
        itens = cursor.fetchall()  # Lista de tuplas (produto_id, quantidade)

        if not itens:
            return render_template('pedido_finalizado.html', mensagem="Erro: Carrinho vazio.")
      
        # 2. Calcular o valor total da compra sem desconto
        valor_total_sem_desconto = 0
        precos_por_produto = {}  # Dicionário para armazenar preços antes do desconto
  
        for produto_id, quantidade in itens:
            cursor.execute("SELECT preco_venda FROM produtos WHERE id = %s;", (produto_id,))
            preco_atual = cursor.fetchone()

            if preco_atual:
                preco_unitario = preco_atual[0]
                preco_total = quantidade * preco_unitario
                precos_por_produto[produto_id] = preco_total  # Armazena o valor sem desconto
                valor_total_sem_desconto += preco_total  # Soma o total geral
       
        # Evitar erro de divisão por zero
        if valor_total_sem_desconto == 0:
            return render_template('pedido_finalizado.html', mensagem="Erro: Total da compra inválido.")

        # Evitar que o desconto seja maior que o valor total da compra
        desconto_total = min(desconto_total, valor_total_sem_desconto)
        # 3. Aplicar desconto proporcionalmente
        for produto_id, quantidade in itens:
            preco_total_original = float(precos_por_produto[produto_id])
            valor_total_sem_desconto = float(valor_total_sem_desconto)

            # Calcula a proporção do desconto para este produto
            desconto_proporcional = float((preco_total_original / valor_total_sem_desconto) * desconto_total)
           
            preco_total_com_desconto = preco_total_original - desconto_proporcional
           
            # Garantir que o valor seja formatado corretamente para duas casas decimais
            preco_total_com_desconto = round(preco_total_com_desconto, 2)

            preco_total_com_desconto = Decimal(preco_total_com_desconto)

            # Inserir na tabela vendas
            cursor.execute("""INSERT INTO vendas (produto_id, quantidade_vendida, preco_total, tipo_pagamento) VALUES (%s, %s, %s, %s);""", (produto_id, quantidade, preco_total_com_desconto, tipo_pagamento))
            
        # 4. Excluir os itens do carrinho após registrar a venda
        cursor.execute("DELETE FROM itens_no_carrinho;")

        # 5. Confirmar a transação no banco
        banco.commit()
        mensagem = f"Pagamento finalizado com sucesso! Desconto total aplicado: R$ {desconto_total:.2f}"

    except Exception as e:
        banco.rollback()  # Reverte mudanças se houver erro
        mensagem = f"Erro ao finalizar pagamento: {str(e)}"

    finally:
        cursor.close()
        banco.close()

    return render_template('pedido_finalizado.html', mensagem=mensagem)


# Função para recurar senha do usuario
@app.route('/pagina_recuperar_senha', methods=['GET','POST'])
def pagina_recuperar_senha():
    return render_template('pagina_recuperar_senha.html')

#Função Enviar email de recuperar senha
@app.route('/enviar_email_recuperar_senha', methods=['POST'])
def enviar_email_recuperar_senha():
    data = request.json
    email = data.get('email')

    banco = conexao_bd()
    cursor = banco.cursor()

    sql = 'SELECT nome FROM vendedores WHERE email = %s'
    cursor.execute(sql, (email,))
    usuario = cursor.fetchone()

    if usuario is not None:
        # Gerar um link de redefinição de senha (exemplo básico)
        token_redefinicao = str(uuid.uuid4())
        expiracao = datetime.now() + timedelta(minutes=15)
        link_redefinicao = f"http://127.0.0.1:5000/pagina_nova_senha"

        sql = 'UPDATE vendedores SET id_token = %s, token_expiracao = %s WHERE email = %s'
        cursor.execute(sql, (token_redefinicao, expiracao, email,))
        banco.commit()
        banco.close()

        # Enviar o e-mail
        enviar_email_recuperacao(email, link_redefinicao, token_redefinicao, expiracao)

        return jsonify(success=True, message='Email de recuperação enviado!'), 200
    else:
        return jsonify(success=False, message='Email não cadastrado!'), 400

#Função Enviar email de recuperar senha
def enviar_email_recuperacao(email_destinatario, link_redefinicao, token_redefinicao, expiracao):
    data_hora_formatada = expiracao.strftime('%d/%m/%Y %H:%M')

    msg = EmailMessage()
    msg.set_content(f'''Clique no link abaixo para redefinir sua senha:
                    
https://app-controle-estoque.onrender.com//pagina_nova_senha?token={token_redefinicao}
    
Validade: 15 Minutos
Expira em: {data_hora_formatada}
''')
    msg['Subject'] = 'Redefinição de Senha'
    msg['From'] = 'luanrodriguesribeiro@gmail.com'  # Substitua pelo seu e-mail
    msg['To'] = email_destinatario

    servidor_smtp = 'smtp.gmail.com'
    porta_smtp = 587
    usuario_smtp = 'luanrodriguesribeiro@gmail.com'  # Substitua pelo seu e-mail
    senha_smtp = 'adfg lpxt nauw cbqv'  # Substitua pela sua senha

    with smtplib.SMTP(servidor_smtp, porta_smtp) as servidor:
        servidor.starttls()
        servidor.login(usuario_smtp, senha_smtp)
        servidor.send_message(msg)

# Função que acessa pagina para cadastra nova senha
@app.route('/pagina_nova_senha', methods=['GET'])
def pagina_nova_senha():
    return render_template('pagina_nova_senha.html')

# Função que gera salva na senha no banco de dados
@app.route('/nova_senha', methods=['POST', 'GET'])
def nova_senha():
    data = request.json
    nova_senha = data.get('novaSenha')
    token = data.get('token')
   

    banco = conexao_bd()
    cursor = banco.cursor()

    # Verifica o token e se ele não expirou
    sql = 'SELECT id_usuario, token_expiracao FROM vendedores WHERE id_token = %s'
    cursor.execute(sql, (token,))
    resultado = cursor.fetchone()

    if not resultado:
        return jsonify(success=False, message='Token inválido ou expirado'), 400

    id_usuario, expiracao_token = resultado

    # Obtém a hora atual no fuso horário local
    hora_local_atual = datetime.now()
    # Formata a data e hora para obter apenas 'YYYY-MM-DD HH:MM'
    hora_formatada = hora_local_atual.strftime('%Y-%m-%d %H:%M')
    expiracao_token_formatada = expiracao_token.strftime('%Y-%m-%d %H:%M')

    # Verifica se expiracao_token é timezone-aware, se não for, torná-lo
    if expiracao_token.tzinfo is None:
        expiracao_token = expiracao_token.replace(tzinfo=timezone.utc)

    if hora_formatada > expiracao_token_formatada:
        return jsonify(success=False, message='Token expirado'), 400

    # Atualiza a senha no banco de dados
    nova_senha_hash = generate_password_hash(nova_senha)
    sql = 'UPDATE vendedores SET senha = %s, id_token = NULL, token_expiracao = NULL WHERE id_usuario = %s'
    cursor.execute(sql, (nova_senha_hash, id_usuario))
    banco.commit()

    return jsonify(success=True, message='Senha alterada com sucesso'), 200


if __name__ == '__main__':
    #app.run()
    app.run(debug=True)
    #app.run(host='192.168.0.110')

 