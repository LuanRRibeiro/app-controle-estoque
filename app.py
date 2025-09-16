# '''Aplicativo WEB - Projeto Integrado I'''

import os
import re
import smtplib
import secrets
import hashlib
from decimal import Decimal
from math import ceil
from urllib.parse import urlsplit, urlparse
import mimetypes
import pandas as pd
from prophet import Prophet
from psycopg2.extras import execute_values




import psycopg2
from psycopg2.extras import RealDictCursor

from flask import Flask, request, redirect, render_template, session,url_for, jsonify, flash

from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash  # para validar pbkdf2/scrypt legados
from email.message import EmailMessage
from email.utils import formataddr

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

from google.cloud import storage
from google.oauth2 import service_account

from dotenv import load_dotenv

# ====== Argon2id (senha) ======
from argon2 import PasswordHasher, exceptions as argon2_exc
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

# Opcional: pepper (segredo do app) — defina em .env
PEPPER = os.getenv("PASSWORD_PEPPER", "")

load_dotenv()  # carrega variáveis do .env

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")  # troque em produção

# Timezone para exibir horário no e-mail (apenas apresentação)
try:
    TZ_BR = ZoneInfo("America/Sao_Paulo")
except Exception:
    TZ_BR = None

carrinho_compras = []

# ===============================
# Conexão com o Banco de Dados
# ===============================
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

# ===============================
# Helpers gerais
# ===============================
def esta_autenticado():
    return 'username' in session

def _is_sha256_hex(s: str) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)

def hash_token(raw: str) -> str:
    """Hash (SHA-256) do token de redefinição para guardar no BD."""
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def hash_senha_argon2(plain: str) -> str:
    """Hash de senha com Argon2id + pepper opcional."""
    return ph.hash(plain + PEPPER)

def verificar_senha_argon2(hash_bd: str, senha: str) -> tuple[bool, str | None]:
    """Verifica Argon2id. Retorna (ok, novo_hash_ou_None) se precisar rehash."""
    try:
        ok = ph.verify(hash_bd, senha + PEPPER)
        if ok and ph.check_needs_rehash(hash_bd):
            return True, ph.hash(senha + PEPPER)
        return ok, None
    except (argon2_exc.VerifyMismatchError, argon2_exc.InvalidHash):
        return False, None

def build_reset_link(token: str) -> str:
    """
    Monta o link de redefinição conforme ambiente.
    - Produção: APP_BASE_URL (ex.: https://app-controle-estoque.onrender.com)
    - Dev: usa http/https conforme USE_HTTPS
    """
    base = os.getenv('APP_BASE_URL')
    if base:
        return f"{base.rstrip('/')}{url_for('pagina_nova_senha', token=token, _external=False)}"
    use_https = os.getenv("USE_HTTPS", "false").lower() == "true"
    return url_for('pagina_nova_senha', token=token, _external=True, _scheme='https' if use_https else 'http')

def enviar_email_recuperacao(email_destinatario: str, link_redefinicao: str, expiracao_utc_naive: datetime):
    """Envia e-mail com link de redefinição. Usa SMTP_* do ambiente."""
    app_name = os.getenv("APP_NAME", "Controle de Estoque")

    servidor_smtp = os.getenv("SMTP_HOST", "smtp.gmail.com")
    porta_smtp    = int(os.getenv("SMTP_PORT", "465"))  # 465=SSL; 587=STARTTLS
    usuario_smtp  = os.getenv("SMTP_USER")              # ex.: seu@gmail.com
    senha_smtp    = os.getenv("SMTP_PASS")              # App Password (Gmail)
    remetente     = os.getenv("SMTP_FROM") or usuario_smtp
    remetente_nm  = os.getenv("SMTP_FROM_NAME", app_name)

    if not usuario_smtp:
        raise RuntimeError("Config faltando: defina SMTP_USER")
    if not senha_smtp:
        raise RuntimeError("Config faltando: defina SMTP_PASS")
    if not remetente:
        raise RuntimeError("Config faltando: defina SMTP_FROM ou SMTP_USER")

    # expiração exibida no fuso do Brasil (apenas para o e-mail)
    exp_aware = expiracao_utc_naive.replace(tzinfo=timezone.utc)
    exp_local = exp_aware.astimezone(TZ_BR) if TZ_BR else exp_aware
    exp_str = exp_local.strftime("%d/%m/%Y %H:%M")

    msg = EmailMessage()
    msg["Subject"] = "Redefinição de Senha"
    msg["From"] = formataddr((remetente_nm or "", remetente))
    msg["To"] = email_destinatario

    texto = (
        f"{app_name}\n\n"
        "Clique no link abaixo para redefinir sua senha:\n\n"
        f"{link_redefinicao}\n\n"
        "Validade: 15 minutos\n"
        f"Expira em: {exp_str}\n\n"
        "Se você não solicitou, ignore este e-mail."
    )
    html = f"""
    <html><body>
      <p>Você solicitou a redefinição de senha no <strong>{app_name}</strong>.</p>
      <p><a href="{link_redefinicao}" style="display:inline-block;padding:10px 16px;
         text-decoration:none;border-radius:4px;border:1px solid #ccc;">Redefinir senha</a></p>
      <p>Validade: 15 minutos<br>Expira em: <strong>{exp_str}</strong></p>
      <p>Se você não solicitou, ignore este e-mail.</p>
    </body></html>
    """
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    if porta_smtp == 465:
        with smtplib.SMTP_SSL(servidor_smtp, porta_smtp) as s:
            s.login(usuario_smtp, senha_smtp)
            s.send_message(msg)
    else:
        with smtplib.SMTP(servidor_smtp, porta_smtp) as s:
            s.starttls()
            s.login(usuario_smtp, senha_smtp)
            s.send_message(msg)

# ===============================
# Login / Logout
# ===============================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = (request.form.get('password') or '')

        if not email or not password:
            return jsonify({'error': 'Email e senha são obrigatórios'}), 400

        banco = conexao_bd()
        try:
            cursor = banco.cursor()
            cursor.execute('SELECT id_usuario, senha FROM vendedores WHERE email = %s', (email,))
            usuario = cursor.fetchone()

            if not usuario:
                return jsonify({'error': 'Nome de usuário ou senha inválido(a)'}), 401

            id_usuario, senha_hash = usuario
            ok = False

            # 1) Tenta Argon2id (padrão atual)
            ok, novo_hash = verificar_senha_argon2(senha_hash or '', password)
            if ok and novo_hash:
                cursor.execute('UPDATE vendedores SET senha = %s WHERE id_usuario = %s', (novo_hash, id_usuario))
                banco.commit()

            # 2) Se não for Argon2id, tenta pbkdf2/scrypt do Werkzeug e migra para Argon2id
            if not ok and senha_hash and (senha_hash.startswith('pbkdf2:') or senha_hash.startswith('scrypt:')):
                ok = check_password_hash(senha_hash, password)
                if ok:
                    novo_hash = hash_senha_argon2(password)
                    cursor.execute('UPDATE vendedores SET senha = %s WHERE id_usuario = %s', (novo_hash, id_usuario))
                    banco.commit()

            # 3) SHA-256 "puro" legado — aceita 1x e migra
            if not ok and _is_sha256_hex(senha_hash or ''):
                ok = (hashlib.sha256(password.encode('utf-8')).hexdigest() == senha_hash)
                if ok:
                    novo_hash = hash_senha_argon2(password)
                    cursor.execute('UPDATE vendedores SET senha = %s WHERE id_usuario = %s', (novo_hash, id_usuario))
                    banco.commit()

            if not ok:
                return jsonify({'error': 'Nome de usuário ou senha inválido(a)'}), 401

            # contabiliza acesso e cria sessão
            cursor.execute('UPDATE vendedores SET acesso = COALESCE(acesso, 0) + 1 WHERE id_usuario = %s', (id_usuario,))
            banco.commit()

            session['user_id'] = id_usuario
            session['username'] = email
            return jsonify({'error': None}), 200

        except Exception as e:
            try: banco.rollback()
            except: pass
            app.logger.exception('Erro no login: %s', e)
            return jsonify({'error': 'Não foi possível processar sua solicitação agora.'}), 500
        finally:
            try: cursor.close()
            except: pass
            try: banco.close()
            except: pass

    return render_template('login.html', error=None)

@app.route('/erro')
def erro():
    return render_template('login_erro.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ===============================
# Painel e demais rotas do app
# ===============================
@app.route('/painel')
def painel():
    if not esta_autenticado():
        return redirect(url_for('login'))

    carrinho_compras.clear()
    email = session.get('username')

    termo_busca = request.args.get('search', '').strip().lower()
    produtos_por_pagina = 10
    pagina_atual = request.args.get('page', 1, type=int)
    offset = (pagina_atual - 1) * produtos_por_pagina

    sql_buscar_produtos = '''
        SELECT id, nome, descricao, quantidade, preco_venda, caminho_imagem
        FROM produtos
        WHERE LOWER(nome) LIKE %s OR LOWER(descricao) LIKE %s
        ORDER BY id ASC
        LIMIT %s OFFSET %s
    '''
    busca_param = f"%{termo_busca}%"

    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute(sql_buscar_produtos, (busca_param, busca_param, produtos_por_pagina, offset))
    produtos = cursor.fetchall()

    lista_produtos = [{
        'id': produto[0],
        'nome': produto[1],
        'descricao': produto[2],
        'quantidade': produto[3],
        'preco_venda': float(produto[4]),
        'imagem': produto[5]
    } for produto in produtos if produto[3] > 0]

    cursor.execute("SELECT COUNT(*) FROM produtos WHERE LOWER(nome) LIKE %s OR LOWER(descricao) LIKE %s", (busca_param, busca_param))
    total_produtos = cursor.fetchone()[0]
    total_paginas = 0 if total_produtos == 0 else (total_produtos + produtos_por_pagina - 1) // produtos_por_pagina

    sql_verificar = '''
        SELECT produto_id, quantidade 
        FROM itens_no_carrinho 
        WHERE usuario_id = (SELECT id_usuario FROM vendedores WHERE email = %s)
    '''
    cursor.execute(sql_verificar, (email,))
    resultado = cursor.fetchall()
    
    for item in resultado:
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

        valor_total = preco * quantidade_selecionada

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

    quantidade_itens_carrinho = calcular_quantidade_total_carrinho(carrinho_compras) if carrinho_compras else 0
    
    return render_template(
        'painel.html',
        produtos=lista_produtos,
        quantidade_itens_carrinho=quantidade_itens_carrinho,
        pagina_atual=pagina_atual,
        total_paginas=total_paginas,
        search=termo_busca
    )

@app.route('/buscar_produtos', methods=['POST'])
def buscar_produtos():
    termo = request.json['termo'].lower()
    if not termo:
        return jsonify([])

    banco = conexao_bd()
    cursor = banco.cursor()

    if termo.isdigit():
        cursor.execute("SELECT * FROM produtos WHERE CAST(quantidade AS integer) >= 1 AND id = %s", (termo,))
    else:
        cursor.execute("SELECT * FROM produtos WHERE CAST(quantidade AS integer) >= 1 AND (LOWER(nome) LIKE %s OR LOWER(descricao) LIKE %s)", ('%' + termo + '%', '%' + termo + '%'))

    produtos = cursor.fetchall()
    cursor.close()
    banco.close()
    
    produtos_json = []
    for produto in produtos:
        produtos_json.append({
            'id': produto[0],
            'nome': produto[1],
            'quantidade': int(produto[2]),
            'descricao': produto[3],
            'preco_compra': produto[4],
            'preco_venda': float(produto[5]),
            'lucro_reais': produto[6],
            'lucro_porcentagem': produto[7],
            'imagem': produto[8]
        })
    return jsonify(produtos_json)

@app.route('/carrinho')
def carrinho():
    if not esta_autenticado():
        return redirect(url_for('login'))

    carrinho_compras.clear()
    email = session.get('username')

    banco = conexao_bd()
    cursor = banco.cursor()
    
    cursor.execute('SELECT id_usuario FROM vendedores WHERE email = %s', (email,))
    resultado_usuario = cursor.fetchone()

    if resultado_usuario:
        id_usuario = resultado_usuario[0]
        cursor.execute('SELECT produto_id, quantidade FROM itens_no_carrinho WHERE usuario_id = %s', (id_usuario,))
        resultado_carrinho = cursor.fetchall()
        
        for item in resultado_carrinho:
            produto_id = item[0]
            quantidade_selecionada = item[1]

            cursor.execute('SELECT nome, descricao, quantidade, preco_venda, caminho_imagem FROM produtos WHERE id = %s', (produto_id,))
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
        return redirect(url_for('login'))
    
    cursor.close()
    banco.close()

    return render_template('carrinho.html', carrinho_compras=carrinho_compras)

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
    
    cursor.execute('SELECT id_usuario FROM vendedores WHERE email = %s', (email,))
    resultado = cursor.fetchone()

    if resultado:
        id_usuario = resultado[0]

        cursor.execute('SELECT COUNT(*) FROM itens_no_carrinho WHERE usuario_id = %s AND produto_id = %s', (id_usuario, produto_id))
        quantidade_produto_no_carrinho = cursor.fetchone()[0]

        if quantidade_produto_no_carrinho > 0:
            cursor.execute('UPDATE itens_no_carrinho SET quantidade = quantidade + %s WHERE usuario_id = %s AND produto_id = %s', (quantidade, id_usuario, produto_id))
        else:
            cursor.execute('INSERT INTO itens_no_carrinho (usuario_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)', (id_usuario, produto_id, quantidade, preco_unitario))

        banco.commit()
        cursor.close()
        banco.close()

        diminuir_quantidade_produto_no_bd(produto['id'], produto['quantidade'], 'adicionar')
        quantidade_itens_carrinho = calcular_quantidade_total_carrinho(carrinho_compras)

        return jsonify({'message': 'Produto adicionado ao carrinho com sucesso', 'quantidadeItens': quantidade_itens_carrinho})
    else:
        cursor.close()
        banco.close()
        return jsonify({'error': 'Usuário não encontrado'}), 404

@app.route('/remover_do_carrinho', methods=['POST'])
def remover_produto_do_carrinho():
    dados_produto = request.json
    produto_id = int(dados_produto.get('id'))

    banco = conexao_bd()
    cursor = banco.cursor()

    cursor.execute('SELECT quantidade FROM itens_no_carrinho WHERE produto_id = %s', (produto_id,))
    quantidade = cursor.fetchone()[0]

    cursor.execute('DELETE FROM itens_no_carrinho WHERE produto_id = %s', (produto_id,))
    banco.commit()

    cursor.close()
    banco.close()
    
    aumentar_quantidade_produto_no_bd(produto_id, quantidade)
    return jsonify({'message': 'Produto removido com sucesso'}), 200

def aumentar_quantidade_produto_no_bd(id_produto, quantidade):
    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute("UPDATE produtos SET quantidade = quantidade + %s WHERE id = %s", (quantidade, id_produto))
    cursor.execute("UPDATE itens_no_carrinho SET quantidade = quantidade - %s WHERE produto_id = %s", (quantidade, int(id_produto)))
    banco.commit()
    cursor.close()
    banco.close()

def diminuir_quantidade_produto_no_bd(id_produto, quantidade, tipo):
    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute("UPDATE produtos SET quantidade = quantidade - %s WHERE id = %s", (quantidade, id_produto))
    if tipo == 'btn_aumentar':
        cursor.execute("UPDATE itens_no_carrinho SET quantidade = quantidade + %s WHERE produto_id = %s", (quantidade, int(id_produto)))
    banco.commit()
    cursor.close()
    banco.close()

def calcular_quantidade_total_carrinho(carrinho_compras):
    sql_verificar = '''
        SELECT SUM(quantidade) AS total_quantidade 
        FROM itens_no_carrinho
        WHERE usuario_id = (SELECT id_usuario FROM vendedores WHERE email = %s) 
    '''
    banco = conexao_bd()
    cursor = banco.cursor()
    email = session.get('username')
    cursor.execute(sql_verificar, (email,))
    quantidade_itens_carrinho = cursor.fetchone()[0] or 0
    cursor.close()
    banco.close()
    return quantidade_itens_carrinho

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
            item['valorTotal'] = nova_quantidade * item['preco']
            break
    if acao == 'btn_aumentar':
        diminuir_quantidade_produto_no_bd(produto['id'], 1, 'btn_aumentar')
    else:
        aumentar_quantidade_produto_no_bd(produto['id'], 1)
    return 'Estoque atualizado com sucesso.', 200

@app.route('/cadastro_produtos')
def cadastro_de_produtos():
    if not esta_autenticado():
        return redirect(url_for('login'))
    return render_template('produtos/cadastro_produtos.html')

def montar_blob_produto(id_produto: int, nome_produto: str, ext: str, usar_nome_no_arquivo=True) -> str:
    """Gera o caminho do blob no GCS.
       usar_nome_no_arquivo=True -> produtos/{id}/NOME.ext
       False -> produtos/{id}/principal.ext (não precisa renomear quando o nome mudar)
    """
    ext = (ext or "").lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    if usar_nome_no_arquivo:
        return f"produtos/{id_produto}/{secure_filename(nome_produto)}{ext}"
    return f"produtos/{id_produto}/principal{ext}"

@app.route('/adicionar_produto', methods=['POST'])
def pagina_adicionar_produto():
    nome = request.form['nome'].upper()
    quantidade = int(request.form['quantidade'])
    descricao = request.form['descricao'].upper()
    preco_compra = request.form['preco_compra']
    preco_venda = request.form['preco_venda']
    lucro_reais = request.form['lucro_reais']
    lucro_porcentagem = float(request.form['lucro_porcentagem'].rstrip('%'))

    imagem = request.files.get('imagem')
    tem_upload = bool(imagem and imagem.filename)

    if produto_existe(nome):
        return 'Produto já cadastrado anteriormente!', 409

    # 1) Insere primeiro e pega o ID
    nome_bucket = "bd_imagens"
    URL_PADRAO = f"https://storage.cloud.google.com/{nome_bucket}/sem_imagem.png"

    banco = conexao_bd()
    cursor = banco.cursor()
    sql_ins = """
        INSERT INTO produtos (nome, quantidade, descricao, preco_compra, preco_venda,
                              lucro_reais, lucro_porcentagem, caminho_imagem)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """
    cursor.execute(sql_ins, (nome, quantidade, descricao, preco_compra, preco_venda,
                             lucro_reais, lucro_porcentagem, URL_PADRAO))
    id_produto = cursor.fetchone()[0]
    banco.commit()
    cursor.close()
    banco.close()

    url_final = URL_PADRAO

    # 2) Se tiver imagem, sobe para produtos/{id}/...
    if tem_upload:
        pasta_raiz = os.path.dirname(os.path.realpath(__file__))
        pasta_temp = '/tmp/temp'
        if not os.path.exists(pasta_temp):
            os.makedirs(pasta_temp)

        ext = os.path.splitext(secure_filename(imagem.filename))[1].lower() or ".jpg"

        # Escolha UMA das duas linhas abaixo:
        # A) arquivo com o nome do produto (se o nome mudar, terá que renomear depois):
        blob_destino = montar_blob_produto(id_produto, nome, ext, usar_nome_no_arquivo=True)
        # B) arquivo fixo 'principal.ext' (NÃO precisa renomear quando o nome mudar):
        # blob_destino = montar_blob_produto(id_produto, nome, ext, usar_nome_no_arquivo=False)

        caminho_tmp = os.path.join(pasta_temp, f"tmp-{id_produto}{ext}")
        imagem.save(caminho_tmp)

        # Credenciais GCP (se não estiver setado antes)
        chave = 'projetoteste-398517-0c1513a4a70e.json'
        caminho_arquivo_json = os.path.join(pasta_raiz, chave)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = caminho_arquivo_json

        # Sobe sobrescrevendo (sua função já foi ajustada para deletar se existir)
        fazer_upload_imagem_gcs(nome_bucket, caminho_tmp, blob_destino)
        url_final = f"https://storage.cloud.google.com/{nome_bucket}/{blob_destino}"

        os.remove(caminho_tmp)

        # 3) Atualiza a URL final no produto
        banco = conexao_bd()
        cursor = banco.cursor()
        cursor.execute("UPDATE produtos SET caminho_imagem = %s WHERE id = %s", (url_final, id_produto))
        banco.commit()
        cursor.close()
        banco.close()

    return 'Produto cadastrado com sucesso!', 200

def fazer_upload_imagem_gcs(nome_bucket, caminho_imagem_local, nome_blob_destino):
    cliente = storage.Client()
    bucket = cliente.bucket(nome_bucket)
    blob = bucket.blob(nome_blob_destino)

    # sobrescreve de verdade
    if blob.exists():
        blob.delete()

    content_type = mimetypes.guess_type(nome_blob_destino)[0] or "application/octet-stream"
    blob.upload_from_filename(caminho_imagem_local, content_type=content_type)

def obter_url_imagem(nome_bucket, nome_blob):
    cliente_storage = storage.Client()
    bucket = cliente_storage.bucket(nome_bucket)
    blob = bucket.blob(nome_blob)
    url = blob.generate_signed_url(expiration=timedelta(days=3652))
    return url

def produto_existe(nome_produto):
    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute("SELECT * FROM produtos WHERE nome = %s", (nome_produto,))
    produto = cursor.fetchone()
    cursor.close()
    banco.close()
    return produto is not None

def adicionar_produto(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem):
    if produto_existe(nome):
        return 'Existe'
    else:
        banco = conexao_bd()
        cursor = banco.cursor()
        sql = "INSERT INTO produtos (nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        dados_produto = (nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem)
        cursor.execute(sql, dados_produto)
        banco.commit()
        cursor.close()
        banco.close()
        return 'Cadastrado'

def formatar_valor(valor):
    return f'{valor:.2f}'

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
    return render_template('editar_produto.html', produto=produto)


# ---- HELPERS GCS (substitua/adicione) ----
NOME_BLOB_PADRAO = "sem_imagem.png"

def extrair_nome_blob_da_url(url: str, nome_bucket: str) -> str:
    if not url:
        return ""
    p = urlparse(url)
    partes = p.path.strip("/").split("/")
    if partes and partes[0] == nome_bucket:
        return "/".join(partes[1:])
    return "/".join(partes[1:]) if len(partes) > 1 else (partes[-1] if partes else "")

def eh_imagem_padrao(url: str, nome_bucket: str) -> bool:
    blob = extrair_nome_blob_da_url(url, nome_bucket).lower()
    return blob == NOME_BLOB_PADRAO or blob.endswith("/" + NOME_BLOB_PADRAO)

def montar_url_publica(nome_bucket: str, nome_blob: str) -> str:
    return f"https://storage.cloud.google.com/{nome_bucket}/{nome_blob}"

def montar_nome_blob_padrao(nome_produto: str, id_produto: int, ext_com_ponto: str) -> str:
    base = secure_filename(nome_produto)
    return f"{base}-{id_produto}{ext_com_ponto.lower()}"

def excluir_blob_se_existir(nome_bucket: str, nome_blob: str):
    cliente = storage.Client()
    bucket = cliente.bucket(nome_bucket)
    b = bucket.blob(nome_blob)
    if b.exists():
        b.delete()

def renomear_objeto_gcs_sobrescrever(nome_bucket: str, blob_antigo: str, blob_novo: str):
    cliente = storage.Client()
    bucket = cliente.bucket(nome_bucket)
    origem = bucket.blob(blob_antigo)
    if not origem.exists():
        return
    # apaga destino se existir (evita "-1")
    excluir_blob_se_existir(nome_bucket, blob_novo)
    bucket.copy_blob(origem, bucket, blob_novo)
    origem.delete()

@app.route('/salvar_produto_editado/<int:id_produto>', methods=['POST'])
def salvar_produto_editado(id_produto):
    nome = request.form['nome'].upper()
    quantidade = int(request.form['quantidade'])
    descricao = request.form['descricao'].upper()
    preco_compra = request.form['preco_compra']
    preco_venda = request.form['preco_venda']
    lucro_reais = request.form['lucro_reais']
    lucro_porcentagem = float(request.form['lucro_porcentagem'].rstrip('%'))

    imagem = request.files.get('imagem')
    enviado = 'sim' if (imagem and imagem.filename) else 'nao'

    # Busca produto atual
    banco = conexao_bd()
    cursor = banco.cursor()
    cursor.execute("SELECT nome, caminho_imagem FROM produtos WHERE id = %s", (id_produto,))
    produto = cursor.fetchone()
    cursor.close(); banco.close()

    nome_produto = produto[0] if produto else None
    imagem_url = produto[1] if produto else None

    # Configurações GCS
    nome_bucket = "bd_imagens"
    URL_SEM_IMAGEM = montar_url_publica(nome_bucket, NOME_BLOB_PADRAO)

    # Valor padrão de url_final = atual (ou padrão)
    url_final = imagem_url or URL_SEM_IMAGEM

    if enviado == 'sim':
        # ------ NOVA IMAGEM ENVIADA ------
        pasta_raiz = os.path.dirname(os.path.realpath(__file__))
        pasta_temp = '/tmp/temp'
        os.makedirs(pasta_temp, exist_ok=True)

        ext_nova = os.path.splitext(secure_filename(imagem.filename))[1].lower()
        if not ext_nova:
            # se não der pra extrair, tenta herdar a atual; senão usa .jpg
            ext_atual = os.path.splitext(extrair_nome_blob_da_url(imagem_url, nome_bucket))[1].lower() if imagem_url else ""
            ext_nova = ext_atual or ".jpg"

        nome_blob_destino = montar_nome_blob_padrao(nome, id_produto, ext_nova)

        caminho_temp = os.path.join(pasta_temp, secure_filename(f"{nome}-{id_produto}{ext_nova}"))
        imagem.save(caminho_temp)

        # Credenciais (ajuste se já inicializa em outro lugar)
        chave = 'projetoteste-398517-0c1513a4a70e.json'
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(pasta_raiz, chave)

        # Apaga o destino se existir (pra não criar "-1")
        excluir_blob_se_existir(nome_bucket, nome_blob_destino)

        # Se havia imagem antiga e NÃO é a padrão, exclui
        if imagem_url and not eh_imagem_padrao(imagem_url, nome_bucket):
            excluir_imagem_gcs(imagem_url)

        # Faz upload com o nome final determinístico
        fazer_upload_imagem_gcs(nome_bucket, caminho_temp, nome_blob_destino)
        url_final = montar_url_publica(nome_bucket, nome_blob_destino)
        os.remove(caminho_temp)

    else:
        # ------ SEM NOVA IMAGEM ------
        # Se há imagem atual e NÃO é a padrão e o nome mudou -> renomeia no GCS
        if imagem_url and not eh_imagem_padrao(imagem_url, nome_bucket) and (nome_produto != nome):
            blob_atual = extrair_nome_blob_da_url(imagem_url, nome_bucket)
            ext_atual = os.path.splitext(blob_atual)[1] or ".jpg"
            blob_novo = montar_nome_blob_padrao(nome, id_produto, ext_atual)
            if blob_atual != blob_novo:
                renomear_objeto_gcs_sobrescrever(nome_bucket, blob_atual, blob_novo)
                url_final = montar_url_publica(nome_bucket, blob_novo)
        # Se não havia imagem, garante a padrão
        elif not imagem_url:
            url_final = URL_SEM_IMAGEM

    # ------ ATUALIZA BANCO UMA ÚNICA VEZ ------
    resultado = editar_produto_banco_dados(
        nome, quantidade, descricao, preco_compra, preco_venda,
        lucro_reais, lucro_porcentagem, url_final, id_produto
    )

    if resultado == 'Cadastrado':
        return 'Produto editado com sucesso!', 200
    else:
        return 'Ocorreu um erro ao editar o produto. Por favor, tente novamente.', 500

def editar_produto_banco_dados(nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem, id_produto):
    banco = conexao_bd()
    cursor = banco.cursor()
    sql = "UPDATE produtos SET nome = %s, quantidade = %s, descricao = %s, preco_compra = %s, preco_venda = %s, lucro_reais = %s, lucro_porcentagem = %s, caminho_imagem = %s WHERE id = %s"
    dados_produto = (nome, quantidade, descricao, preco_compra, preco_venda, lucro_reais, lucro_porcentagem, caminho_imagem, id_produto)
    cursor.execute(sql, dados_produto)
    banco.commit()
    cursor.close()
    banco.close()
    return 'Cadastrado'

@app.route('/listar_produtos')
def listar_produtos():
    search = request.args.get('search', '')
    fora_de_estoque = request.args.get('fora_de_estoque', '0') == '1'
    pagina = request.args.get('pagina', 1, type=int)
    itens_por_pagina = 10
    offset = (pagina - 1) * itens_por_pagina

    produtos = []
    banco = conexao_bd()
    cursor = banco.cursor()

    sql = "SELECT * FROM produtos WHERE 1=1"
    params = []

    if fora_de_estoque:
        sql += " AND quantidade = 0"
    else:
        sql += " AND quantidade > 0"

    if search:
        try:
            id_busca = int(search)
            sql += " AND id = %s"
            params.append(id_busca)
        except ValueError:
            sql += " AND nome ILIKE %s"
            params.append(f'%{search}%')

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
    cursor.execute("SELECT caminho_imagem FROM produtos WHERE id = %s", (id,))
    produto = cursor.fetchone()

    if produto:
        imagem_url = produto[0]
        cursor.execute("DELETE FROM produtos WHERE id = %s", (id,))
        banco.commit()
        cursor.close()
        banco.close()
        if imagem_url:
            excluir_imagem_gcs(imagem_url)
    return redirect(url_for('listar_produtos'))

def excluir_imagem_gcs(imagem_url):
    pasta_raiz = os.path.dirname(os.path.realpath(__file__))
    caminho_chave = os.path.join(pasta_raiz, 'projetoteste-398517-0c1513a4a70e.json')
    credentials = service_account.Credentials.from_service_account_file(caminho_chave)
    storage_client = storage.Client(credentials=credentials)
    nome_bucket = 'bd_imagens'

    parsed_url = urlsplit(imagem_url)
    path = parsed_url.path
    nome_blob = path.lstrip('/').replace(f'{nome_bucket}/', '', 1)
    
    if nome_blob:
        bucket = storage_client.bucket(nome_bucket)
        blob = bucket.blob(nome_blob)
        if nome_blob != 'sem_imagem.png':
            try:
                blob.delete()
            except Exception as e:
                print(f"Erro ao excluir a imagem: {e}")
    else:
        print("URL de imagem inválida.")

@app.route('/pagina_pagamento', methods=['GET'])
def pagina_pagamento():
    total = request.args.get('total', 0.00)
    return render_template('pagamento.html', total=float(total))

@app.route('/finalizar_pagamento', methods=['POST'])
def finalizar_pagamento():
    banco = conexao_bd()
    cursor = banco.cursor()
    try:
        desconto_total = float(request.form.get('desconto', 0))
        tipo_pagamento = request.form.get('tipo_pagamento', 'não informado')
        
        cursor.execute("SELECT produto_id, quantidade FROM itens_no_carrinho;")
        itens = cursor.fetchall()
        if not itens:
            return render_template('pedido_finalizado.html', mensagem="Erro: Carrinho vazio.")
      
        valor_total_sem_desconto = 0
        precos_por_produto = {}
  
        for produto_id, quantidade in itens:
            cursor.execute("SELECT preco_venda FROM produtos WHERE id = %s;", (produto_id,))
            preco_atual = cursor.fetchone()
            if preco_atual:
                preco_unitario = preco_atual[0]
                preco_total = quantidade * preco_unitario
                precos_por_produto[produto_id] = preco_total
                valor_total_sem_desconto += preco_total
       
        if valor_total_sem_desconto == 0:
            return render_template('pedido_finalizado.html', mensagem="Erro: Total da compra inválido.")

        desconto_total = min(desconto_total, valor_total_sem_desconto)

        for produto_id, quantidade in itens:
            preco_total_original = float(precos_por_produto[produto_id])
            base_total = float(valor_total_sem_desconto)
            desconto_proporcional = float((preco_total_original / base_total) * desconto_total)
            preco_total_com_desconto = round(preco_total_original - desconto_proporcional, 2)
            preco_total_com_desconto = Decimal(preco_total_com_desconto)
            cursor.execute("""INSERT INTO vendas (produto_id, quantidade_vendida, preco_total, tipo_pagamento) VALUES (%s, %s, %s, %s);""", (produto_id, quantidade, preco_total_com_desconto, tipo_pagamento))
            
        cursor.execute("DELETE FROM itens_no_carrinho;")
        banco.commit()
        mensagem = f"Pagamento finalizado com sucesso! Desconto total aplicado: R$ {desconto_total:.2f}"

    except Exception as e:
        banco.rollback()
        mensagem = f"Erro ao finalizar pagamento: {str(e)}"
    finally:
        cursor.close()
        banco.close()

    return render_template('pedido_finalizado.html', mensagem=mensagem)

# ===============================
# Recuperação de Senha
# ===============================
@app.route('/pagina_recuperar_senha', methods=['GET','POST'])
def pagina_recuperar_senha():
    return render_template('pagina_recuperar_senha.html')

@app.route('/enviar_email_recuperar_senha', methods=['POST'])
def enviar_email_recuperar_senha():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or "").strip().lower()
    generic_msg = 'Se esse e-mail estiver cadastrado, enviaremos instruções para redefinir a senha.'

    if not email:
        return jsonify(success=False, message='Informe um e-mail.'), 400

    banco = conexao_bd()
    try:
        cursor = banco.cursor()
        cursor.execute('SELECT id_usuario FROM vendedores WHERE email = %s', (email,))
        usuario = cursor.fetchone()

        if usuario:
            raw_token = secrets.token_urlsafe(32)     # ~43 chars
            token_hash = hash_token(raw_token)        # 64 hex
            expiracao = datetime.utcnow() + timedelta(minutes=15)  # UTC naive

            cursor.execute('UPDATE vendedores SET id_token = %s, token_expiracao = %s WHERE email = %s', (token_hash, expiracao, email))
            banco.commit()

            link_redefinicao = build_reset_link(raw_token)
            app.logger.info("Reset: link_redefinicao=%s", link_redefinicao)

            try:
                enviar_email_recuperacao(email, link_redefinicao, expiracao)
                app.logger.info("Reset: e-mail enviado para %s", email)
            except Exception as e:
                app.logger.exception("Falha ao enviar e-mail de recuperação: %s", e)

        return jsonify(success=True, message=generic_msg), 200
    except Exception as e:
        try: banco.rollback()
        except: pass
        app.logger.exception("Erro inesperado no fluxo de reset: %s", e)
        return jsonify(success=False, message='Não foi possível processar sua solicitação agora.'), 500
    finally:
        try: banco.close()
        except: pass

@app.route('/pagina_nova_senha', methods=['GET'])
def pagina_nova_senha():
    token = request.args.get('token', '').strip()
    if not token:
        return "Link inválido: token ausente.", 400
    return render_template('pagina_nova_senha.html', token=token)

@app.route('/nova_senha', methods=['POST'])
def nova_senha():
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or request.form.get('token') or '').strip()
    nova  = (data.get('novaSenha') or data.get('senha') or request.form.get('senha') or '').strip()

    if not token or not nova:
        return jsonify(success=False, message='Requisição inválida.'), 400
    if len(nova) < 8:
        return jsonify(success=False, message='A senha deve ter pelo menos 8 caracteres.'), 400

    now_utc = datetime.utcnow()
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()

    banco = conexao_bd()
    try:
        cur = banco.cursor()

        cur.execute('SELECT id_usuario, token_expiracao FROM vendedores WHERE id_token = %s', (token_hash,))
        row = cur.fetchone()
        matched = 'hash'

        if not row:
            cur.execute('SELECT id_usuario, token_expiracao FROM vendedores WHERE id_token = %s', (token,))
            row = cur.fetchone()
            matched = 'plain' if row else None

        if not row:
            app.logger.info("NovaSenha: token não encontrado (hash/plain). len(token)=%d", len(token))
            return jsonify(success=False, message='Link inválido ou expirado.'), 400

        id_usuario, expira_em = row
        app.logger.info("NovaSenha: token via %s; expira_em=%s; now=%s", matched, expira_em, now_utc)

        if expira_em <= now_utc:
            return jsonify(success=False, message='Link inválido ou expirado.'), 400

        senha_hash = hash_senha_argon2(nova)

        cur.execute(
            'UPDATE vendedores SET senha=%s, id_token=NULL, token_expiracao=NULL WHERE id_usuario=%s',
            (senha_hash, id_usuario)
        )
        banco.commit()
        return jsonify(success=True, message='Senha atualizada com sucesso!'), 200

    except Exception as e:
        try: banco.rollback()
        except: pass
        app.logger.exception("Erro ao definir nova senha: %s", e)
        return jsonify(success=False, message='Não foi possível processar sua solicitação agora.'), 500
    finally:
        try: banco.close()
        except: pass

# ===============================
# Relatórios simples
# ===============================
@app.route("/filtro")
def filtro():
    LIMITE = 5  # fácil de ajustar

    conexao = conexao_bd()
    if conexao is None:
        return "Erro ao conectar ao banco"

    try:
        with conexao.cursor() as cursor:
            # UMA consulta para pegar top e bottom usando janela
            cursor.execute("""
                WITH vendas_por_produto AS (
                    SELECT p.nome AS produto, SUM(v.quantidade_vendida) AS total_vendido
                    FROM vendas v
                    JOIN produtos p ON p.id = v.produto_id
                    GROUP BY p.nome
                ),
                posicoes AS (
                    SELECT
                        produto,
                        total_vendido,
                        ROW_NUMBER() OVER (ORDER BY total_vendido DESC, produto) AS pos_desc,
                        ROW_NUMBER() OVER (ORDER BY total_vendido ASC,  produto) AS pos_asc
                    FROM vendas_por_produto
                )
                SELECT 'mais' AS tipo, produto, total_vendido
                FROM posicoes
                WHERE pos_desc <= %s
                UNION ALL
                SELECT 'menos' AS tipo, produto, total_vendido
                FROM posicoes
                WHERE pos_asc <= %s
                ORDER BY tipo, total_vendido DESC, produto
            """, (LIMITE, LIMITE))
            linhas = cursor.fetchall()

            produtos_mais_vendidos = []
            produtos_menos_vendidos = []
            for tipo, produto, total in linhas:
                if tipo == 'mais':
                    produtos_mais_vendidos.append((produto, total))
                else:
                    produtos_menos_vendidos.append((produto, total))

            # Forma de pagamento mais usada (ou "Nenhum dado" se vazio)
            cursor.execute("""
                SELECT tipo_pagamento FROM (
                    SELECT
                        tipo_pagamento,
                        COUNT(*) AS total,
                        ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, tipo_pagamento) AS rn
                    FROM vendas
                    GROUP BY tipo_pagamento
                ) x
                WHERE rn = 1
            """)
            r = cursor.fetchone()
            forma_pagamento = r[0] if r else "Nenhum dado"

    finally:
        conexao.close()

    return render_template(
        "filtro.html",
        produtos_mais_vendidos=produtos_mais_vendidos,
        produtos_menos_vendidos=produtos_menos_vendidos,
        forma_pagamento=forma_pagamento
    )


# Função para carregar vendas apenas dos produtos que precisam de previsão
def datas_faltantes(cur, produto_id, inicio, fim):
    cur.execute("""
        SELECT d::date
        FROM generate_series(%s::date, %s::date, '1 day') d
        EXCEPT
        SELECT data_previsao
        FROM public.previsoes_vendas
        WHERE produto_id = %s
          AND data_previsao BETWEEN %s AND %s
        ORDER BY 1
    """, (inicio, fim, int(produto_id), inicio, fim))
    return [r[0] for r in cur.fetchall()]

def inserir_previsoes(cur, registros):
    if not registros:
        return
    execute_values(cur, """
        INSERT INTO public.previsoes_vendas
            (produto_id, data_previsao, previsao, limite_inferior, limite_superior, data_geracao)
        VALUES %s
        ON CONFLICT (produto_id, data_previsao) DO UPDATE
        SET previsao        = EXCLUDED.previsao,
            limite_inferior = EXCLUDED.limite_inferior,
            limite_superior = EXCLUDED.limite_superior,
            data_geracao    = EXCLUDED.data_geracao
    """, registros, template="(%s,%s,%s,%s,%s,%s)")

# --- carrega vendas apenas de produtos que precisam ---
def carregar_vendas_necessarias(dias_futuros=30, produto_ids=None):
    hoje = datetime.today().date()
    fim  = hoje + timedelta(days=dias_futuros)
    total_dias = (fim - hoje).days + 1

    banco = conexao_bd(); cur = banco.cursor()

    if produto_ids:
        cur.execute("""
            WITH periodo AS (SELECT %s::date AS ini, %s::date AS fim)
            SELECT v.produto_id
            FROM vendas v
            WHERE v.produto_id = ANY(%s)
            GROUP BY v.produto_id
            HAVING COALESCE((
                SELECT COUNT(*)
                FROM public.previsoes_vendas pv, periodo p
                WHERE pv.produto_id = v.produto_id
                  AND pv.data_previsao BETWEEN p.ini AND p.fim
            ), 0) < %s
            ORDER BY 1
        """, (hoje, fim, produto_ids, total_dias))
    else:
        cur.execute("""
            WITH periodo AS (SELECT %s::date AS ini, %s::date AS fim)
            SELECT v.produto_id
            FROM vendas v
            GROUP BY v.produto_id
            HAVING COALESCE((
                SELECT COUNT(*)
                FROM public.previsoes_vendas pv, periodo p
                WHERE pv.produto_id = v.produto_id
                  AND pv.data_previsao BETWEEN p.ini AND p.fim
            ), 0) < %s
            ORDER BY 1
        """, (hoje, fim, total_dias))

    produtos = [r[0] for r in cur.fetchall()]
    if not produtos:
        cur.close(); banco.close()
        return pd.DataFrame(columns=['produto_id','data_venda','quantidade_vendida'])

    cur.execute("""
        SELECT produto_id, data_venda, quantidade_vendida
        FROM vendas
        WHERE produto_id = ANY(%s)
    """, (produtos,))
    dados = cur.fetchall()
    cur.close(); banco.close()

    df = pd.DataFrame(dados, columns=['produto_id','data_venda','quantidade_vendida'])
    if not df.empty:
        df['data_venda'] = pd.to_datetime(df['data_venda'])
    return df

# --- gera previsões e salva no banco ---
def gerar_previsoes_vendas(dias_futuros=30, bloco_insert=5000, produto_ids=None, somente_leitura=False, janela_treinamento_dias=730):
    # ---------------------- datas base do Postgres ----------------------
    banco = conexao_bd(); cur = banco.cursor()
    cur.execute("SELECT CURRENT_DATE")
    hoje = cur.fetchone()[0]                 # date vindo do banco
    fim  = hoje + timedelta(days=dias_futuros)
    agora_ts = datetime.now()

    # ---------------------- SOMENTE LEITURA -----------------------------
    if somente_leitura:
        previsoes_final = {}
        if produto_ids:
            for pid in produto_ids:
                cur.execute("""
                    SELECT data_previsao, previsao, limite_inferior, limite_superior
                    FROM public.previsoes_vendas
                    WHERE produto_id = %s AND data_previsao BETWEEN %s AND %s
                    ORDER BY data_previsao
                """, (int(pid), hoje, fim))
                rows = cur.fetchall()
                if rows:
                    previsoes_final[int(pid)] = [
                        {'ds': r[0].strftime('%Y-%m-%d'), 'yhat': float(r[1]),
                         'yhat_lower': float(r[2]), 'yhat_upper': float(r[3])}
                    for r in rows]
        cur.close(); banco.close()
        return previsoes_final

    # ---------------------- dados necessários ---------------------------
    # tenta usar a versão com filtro de produtos; se não existir, chama sem filtro
    try:
        df = carregar_vendas_necessarias(dias_futuros=dias_futuros, produto_ids=produto_ids)
    except TypeError:
        df = carregar_vendas_necessarias(dias_futuros=dias_futuros)

    previsoes_dict = {}
    buffer_regs = []

    # Se não há nada a gerar, ainda assim devolve leitura do BD para os produtos solicitados
    if df.empty:
        if produto_ids:
            for pid in produto_ids:
                cur.execute("""
                    SELECT data_previsao, previsao, limite_inferior, limite_superior
                    FROM public.previsoes_vendas
                    WHERE produto_id = %s AND data_previsao BETWEEN %s AND %s
                    ORDER BY data_previsao
                """, (int(pid), hoje, fim))
                rows = cur.fetchall()
                if rows:
                    previsoes_dict[int(pid)] = [
                        {'ds': r[0].strftime('%Y-%m-%d'), 'yhat': float(r[1]),
                         'yhat_lower': float(r[2]), 'yhat_upper': float(r[3])}
                    for r in rows]
        # encerra conexão e retorna
        cur.close(); banco.close()
        return previsoes_dict

    # ---------------------- loop por produto ----------------------------
    for produto_id in df['produto_id'].unique():
        # Quais datas realmente faltam no cache?
        faltantes = set(datas_faltantes(cur, produto_id, hoje, fim))

        # Se não faltar nada, só lê para exibir
        if not faltantes:
            cur.execute("""
                SELECT data_previsao, previsao, limite_inferior, limite_superior
                FROM public.previsoes_vendas
                WHERE produto_id = %s AND data_previsao BETWEEN %s AND %s
                ORDER BY data_previsao
            """, (int(produto_id), hoje, fim))
            rows = cur.fetchall()
            if rows:
                previsoes_dict[int(produto_id)] = [
                    {'ds': r[0].strftime('%Y-%m-%d'), 'yhat': float(r[1]),
                     'yhat_lower': float(r[2]), 'yhat_upper': float(r[3])}
                for r in rows]
            continue

        # Série diária do produto (com janela de treino para acelerar)
        serie = (df[df['produto_id'] == produto_id]
                 .groupby('data_venda', as_index=False)['quantidade_vendida']
                 .sum()
                 .rename(columns={'data_venda':'ds', 'quantidade_vendida':'y'}))
        if len(serie) < 2:
            continue

        serie['ds'] = pd.to_datetime(serie['ds'])
        corte = pd.to_datetime(hoje - timedelta(days=janela_treinamento_dias))
        serie = serie[serie['ds'] >= corte]
        serie = serie.set_index('ds').asfreq('D', fill_value=0).reset_index()

        # Ajusta Prophet
        modelo = Prophet(
            weekly_seasonality=True,
            yearly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.95
        )
        modelo.fit(serie)

        # Horizonte necessário: até 'fim' e, no mínimo, até o maior faltante
        max_obs = pd.to_datetime(serie['ds']).max().date()
        periodos_necessarios = max(0, (fim - max_obs).days)
        if faltantes:
            maior_faltante = max(faltantes)
            periodos_necessarios = max(periodos_necessarios, (maior_faltante - max_obs).days)

        # Se ainda assim não há período a prever (pode ocorrer se max_obs >= fim), apenas leia do BD
        if periodos_necessarios <= 0:
            cur.execute("""
                SELECT data_previsao, previsao, limite_inferior, limite_superior
                FROM public.previsoes_vendas
                WHERE produto_id = %s AND data_previsao BETWEEN %s AND %s
                ORDER BY data_previsao
            """, (int(produto_id), hoje, fim))
            rows = cur.fetchall()
            if rows:
                previsoes_dict[int(produto_id)] = [
                    {'ds': r[0].strftime('%Y-%m-%d'), 'yhat': float(r[1]),
                     'yhat_lower': float(r[2]), 'yhat_upper': float(r[3])}
                for r in rows]
            continue

        # Previsão somente do futuro necessário (relativo a max_obs)
        futuro = modelo.make_future_dataframe(
            periods=periodos_necessarios,
            freq='D',
            include_history=False
        )
        fcst = modelo.predict(futuro)
        fcst[['yhat','yhat_lower','yhat_upper']] = fcst[['yhat','yhat_lower','yhat_upper']].clip(lower=0)
        fcst['ds'] = pd.to_datetime(fcst['ds']).dt.date

        # Mantém apenas [hoje..fim] e as datas que realmente faltavam
        fcst = fcst[(fcst['ds'] >= hoje) & (fcst['ds'] <= fim)]
        fcst = fcst[fcst['ds'].isin(faltantes)]

        # Prepara registros para UPSERT (arredonda p/ numeric(10,2))
        regs = [
            (int(produto_id), d, round(float(y), 2), round(float(lo), 2), round(float(up), 2), agora_ts)
            for d, y, lo, up in zip(fcst['ds'], fcst['yhat'], fcst['yhat_lower'], fcst['yhat_upper'])
        ]
        if regs:
            buffer_regs.extend(regs)
            previsoes_dict.setdefault(int(produto_id), [])
            previsoes_dict[int(produto_id)].extend([
                {'ds': d.strftime('%Y-%m-%d'), 'yhat': float(y),
                 'yhat_lower': float(lo), 'yhat_upper': float(up)}
                for (pid, d, y, lo, up, ts) in regs
            ])

        # Flush em blocos para não estourar memória/pacote
        if len(buffer_regs) >= bloco_insert:
            inserir_previsoes(cur, buffer_regs)
            buffer_regs.clear()

    # Insere o que sobrou e commit
    inserir_previsoes(cur, buffer_regs)
    banco.commit()

    # ---------------------- leitura final (cache completo) --------------
    previsoes_final = {}
    # usa a lista filtrada se foi passada; caso contrário, os produtos processados do df
    ids_para_ler = list(produto_ids or df['produto_id'].unique())
    for pid in ids_para_ler:
        cur.execute("""
            SELECT data_previsao, previsao, limite_inferior, limite_superior
            FROM public.previsoes_vendas
            WHERE produto_id = %s AND data_previsao BETWEEN %s AND %s
            ORDER BY data_previsao
        """, (int(pid), hoje, fim))
        rows = cur.fetchall()
        if rows:
            previsoes_final[int(pid)] = [
                {'ds': r[0].strftime('%Y-%m-%d'), 'yhat': float(r[1]),
                 'yhat_lower': float(r[2]), 'yhat_upper': float(r[3])}
            for r in rows]

    cur.close(); banco.close()
    return previsoes_final

# --- rota Flask ---
@app.route('/previsao_vendas')
def previsao_vendas():
    dias_futuros = int(request.args.get('dias', 30))
    pagina = int(request.args.get('pagina', 1))
    por_pagina = 10

    banco = conexao_bd(); cur = banco.cursor()
    cur.execute("SELECT DISTINCT produto_id FROM vendas ORDER BY 1")
    todos = [r[0] for r in cur.fetchall()]
    cur.close(); banco.close()

    total_paginas = max(1, ceil(len(todos) / por_pagina))
    pagina = max(1, min(pagina, total_paginas))
    ini = (pagina - 1) * por_pagina
    fim = ini + por_pagina
    produtos_pagina = todos[ini:fim]

    # 🔑 só gera/atualiza os produtos desta página
    previsoes = gerar_previsoes_vendas(
        dias_futuros=dias_futuros,
        produto_ids=produtos_pagina
    )

    return render_template(
        'previsoes_vendas.html',
        previsoes=previsoes,
        pagina=pagina,
        total_paginas=total_paginas,
        dias_futuros=dias_futuros
    )




if __name__ == '__main__':
    app.run()
    #app.run(debug=True)
    # app.run(host='192.168.0.110')
