import os
import re
import tempfile
from datetime import datetime
from dateutil.relativedelta import relativedelta
from ofxparse import OfxParser
from database import SessionLocal, Cartao, Categoria, Transacao

MAPA_CATEGORIAS = {
    'Alimentação': ['savegnago', 'jau serve', 'padaria', 'burger', 'food', 'fartura', 'frios', 'sorvetes', 'cafe', 'pastel', 'restaurante', 'cooking', 'verdura'],
    'Transporte': ['sem*parar', 'zul', 'drive', 'stop car', 'combustivel', 'posto'],
    'Assinaturas & Serviços': ['netflix', 'spotify', 'google', 'microsoft', 'wellhub', 'vivo', 'ultravioleta', 'apple'],
    'Saúde': ['farmacia', 'drogaria', 'raia'],
    'Compras & Eletrônicos': ['shopee', 'mercadolivre', 'magalu', 'lenovo', 'americanas'],
    'Cuidados Pessoais': ['barbearia', 'passadoria', 'facility'],
    'Financiamento & Taxas': ['parcelamento de fatura', 'boleto no crédito', 'pix no crédito']
}

def categorizar_transacao(descricao: str) -> str:
    desc_lower = descricao.lower()
    for categoria, palavras in MAPA_CATEGORIAS.items():
        if any(palavra in desc_lower for palavra in palavras):
            return categoria
    return 'Outros'

def extrair_parcelas(memo: str):
    match = re.search(r'(\d{1,2})\s*/\s*(\d{1,2})', memo)
    if match:
        p_atual = int(match.group(1))
        p_total = int(match.group(2))
        if 1 <= p_atual <= p_total <= 60:
            return p_atual, p_total
    return 1, 1

def limpar_nome_base(descricao: str) -> str:
    # Remove marcações de parcela para comparar nomes (ex: "Edidesk - Parcela 3/10" -> "edidesk")
    nome = re.sub(r'[-–]?\s*parcela\s*\d+\s*/\s*\d+', '', descricao, flags=re.IGNORECASE)
    nome = re.sub(r'[-–]?\s*\d+\s*/\s*\d+', '', nome)
    return nome.strip().lower()

def calcular_fatura_mes(data_transacao: datetime, dia_corte: int = 11) -> str:
    if data_transacao.day >= dia_corte:
        fatura_dt = data_transacao + relativedelta(months=1)
    else:
        fatura_dt = data_transacao
    return fatura_dt.strftime("%Y-%m")

def importar_fatura_ofx(conteudo, nome_cartao: str = "Nubank"):
    session = SessionLocal()
    
    cartao = session.query(Cartao).filter_by(nome=nome_cartao).first()
    if not cartao:
        cartao = Cartao(nome=nome_cartao, fechamento_dia=11, vencimento_dia=19)
        session.add(cartao)
        session.commit()

    # Criação de arquivo temporário seguro para Windows
    temp_dir = tempfile.gettempdir()
    caminho_temp = os.path.join(temp_dir, f"temp_fatura_{datetime.now().timestamp()}.ofx")

    if isinstance(conteudo, bytes):
        with open(caminho_temp, "wb") as f_temp:
            f_temp.write(conteudo)
    elif hasattr(conteudo, "read"):
        with open(caminho_temp, "wb") as f_temp:
            dados = conteudo.read()
            if isinstance(dados, str):
                dados = dados.encode("latin-1")
            f_temp.write(dados)
    else:
        caminho_temp = conteudo

    try:
        with open(caminho_temp, "rb") as f_leitura:
            ofx = OfxParser.parse(f_leitura)
    finally:
        if os.path.exists(caminho_temp) and caminho_temp != conteudo:
            try:
                os.remove(caminho_temp)
            except OSError:
                pass

    categorias_db = {c.nome: c for c in session.query(Categoria).all()}
    
    # Busca compras parceladas que já foram atribuídas à mãe anteriormente
    transacoes_mae = session.query(Transacao.descricao).filter(
        Transacao.da_mae == True, 
        Transacao.total_parcelas > 1
    ).all()
    nomes_base_mae = {limpar_nome_base(t[0]) for t in transacoes_mae}

    novas_transacoes = 0

    for t in ofx.account.statement.transactions:
        if t.type == 'credit' or t.amount >= 0:
            continue

        descricao = t.memo.strip()
        valor = abs(float(t.amount))
        data = t.date
        
        parcela_atual, total_parcelas = extrair_parcelas(descricao)
        nome_cat = categorizar_transacao(descricao)
        fatura_mes = calcular_fatura_mes(data, dia_corte=cartao.fechamento_dia)

        # Regra automática: se é uma compra parcelada que já era dela, marca como dela
        e_da_mae = False
        if total_parcelas > 1:
            nome_simplificado = limpar_nome_base(descricao)
            if any(nome_simplificado == base or base in nome_simplificado for base in nomes_base_mae):
                e_da_mae = True

        if nome_cat not in categorias_db:
            nova_cat = Categoria(nome=nome_cat)
            session.add(nova_cat)
            session.flush()
            categorias_db[nome_cat] = nova_cat

        categoria_obj = categorias_db[nome_cat]

        existe = session.query(Transacao).filter_by(
            data=data,
            descricao=descricao,
            valor=valor,
            cartao_id=cartao.id
        ).first()

        if not existe:
            transacao = Transacao(
                data=data,
                descricao=descricao,
                valor=valor,
                fatura_mes=fatura_mes,
                parcela_atual=parcela_atual,
                total_parcelas=total_parcelas,
                da_mae=e_da_mae,
                cartao_id=cartao.id,
                categoria_id=categoria_obj.id
            )
            session.add(transacao)
            novas_transacoes += 1

    session.commit()
    session.close()
    return novas_transacoes