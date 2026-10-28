import io
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from ofxparse import OfxParser
from database import SessionLocal, Transacao, Cartao, Categoria

def limpar_nome_base(descricao: str) -> str:
    """
    Remove marcadores de parcelas como '01/10', '(2/5)', ' - Parcela 3'
    para permitir agrupamentos consistentes de compras parceladas.
    """
    padrao = r'(\s*[\(\[\-]?\s*\d+\s*[\/\-]\s*\d+\s*[\)\]]?|\s*-\s*parcela\s*\d+)'
    descricao_limpa = re.sub(padrao, '', descricao, flags=re.IGNORECASE)
    return descricao_limpa.strip()

def extrair_parcelas(descricao: str):
    """
    Identifica parcelas no formato '02/10' ou '3/12'.
    Retorna (parcela_atual, total_parcelas). Se não houver, retorna (1, 1).
    """
    padrao = r'(\d{1,2})\s*[\/\-]\s*(\d{1,2})'
    match = re.search(padrao, descricao)
    if match:
        atual = int(match.group(1))
        total = int(match.group(2))
        if 1 <= atual <= total:
            return atual, total
    return 1, 1

def calcular_fatura_mes(data_transacao: datetime, dia_fechamento: int = 11) -> str:
    """
    Calcula a competência da fatura (YYYY-MM).
    Se a transação ocorrer no dia de fecho ou após, pertence à fatura do mês seguinte.
    """
    if data_transacao.day >= dia_fechamento:
        data_fatura = data_transacao + relativedelta(months=1)
    else:
        data_fatura = data_transacao
    return data_fatura.strftime("%Y-%m")

def importar_fatura_ofx(conteudo_bytes: bytes, nome_cartao: str = "Nubank", user_id: int = None) -> int:
    """
    Analisa o ficheiro OFX e persiste as transações no PostgreSQL vinculadas ao user_id.
    Evita registos duplicados verificando unicidade por utilizador, data, descrição e valor.
    """
    ofx_file = io.BytesIO(conteudo_bytes)
    ofx = OfxParser.parse(ofx_file)
    
    session = SessionLocal()
    
    # Garante a existência do registo do cartão
    cartao = session.query(Cartao).filter_by(nome=nome_cartao).first()
    if not cartao:
        cartao = Cartao(nome=nome_cartao)
        session.add(cartao)
        session.flush()

    # Categoria padrão para novas transações
    cat_padrao = session.query(Categoria).filter_by(nome="Outros").first()
    if not cat_padrao:
        cat_padrao = Categoria(nome="Outros")
        session.add(cat_padrao)
        session.flush()

    total_importadas = 0

    for conta in ofx.accounts:
        for t in conta.statement.transactions:
            # Em cartões de crédito, compras surgem normalmente com valor negativo no OFX
            valor = abs(float(t.amount))
            data_dt = t.date
            descricao = t.memo.strip() if t.memo else (t.payee.strip() if t.payee else "Transação sem descrição")
            
            # Validação anti-duplicação filtrada pelo user_id do titular da conta
            duplicada = session.query(Transacao).filter(
                Transacao.user_id == user_id,
                Transacao.data == data_dt.date(),
                Transacao.descricao == descricao,
                Transacao.valor == valor
            ).first()

            if duplicada:
                continue

            parcela_atual, total_parcelas = extrair_parcelas(descricao)
            fatura_mes = calcular_fatura_mes(data_dt)

            nova_transacao = Transacao(
                user_id=user_id,
                cartao_id=cartao.id,
                categoria_id=cat_padrao.id,
                data=data_dt.date(),
                descricao=descricao,
                valor=valor,
                fatura_mes=fatura_mes,
                parcela_atual=parcela_atual,
                total_parcelas=total_parcelas,
                da_mae=False
            )
            session.add(nova_transacao)
            total_importadas += 1

    session.commit()
    session.close()
    
    return total_importadas