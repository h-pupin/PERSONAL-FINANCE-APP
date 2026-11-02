import io
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from ofxparse import OfxParser
from database import SessionLocal, Transacao, Cartao, Categoria

REGRAS_CATEGORIAS = {
    "Supermercado": [
        "savegnago", "cogeb", "fartura", "minuto pa", "frios estrela", 
        "mercado", "hortifruti", "vovo lucia"
    ],
    "Lazer": [
        "burger king", "ifood", "99food", "padaria", "cooking", "boteco", 
        "cafe", "catarinocafe", "sorvete", "dubelato", "comboio", "yes cooking",
        "art bakery", "guanabara", "planalto", "nopinhabeach", "open bar", "restaurante"
    ],
    "Carro": [
        "sem*parar", "semparar", "zul", "uber", "99app", "posto", "combustivel", 
        "estacionamento", "oficina", "mecanica", "lavacar"
    ],
    "Assinaturas & Serviços": [
        "spotify", "netflix", "apple", "google", "microsoft", "wellhub", 
        "amazon credito", "ifd*ifood club", "ultravioleta", "vivo", "claro", 
        "tim", "cpfl", "sabesp", "boleto", "movame"
    ],
    "Farmácia e Saúde": [
        "drogaria", "farmacia", "kalmia", "medicamento", "hospital", "saude", "clinica"
    ],
    "Compras": [
        "shopee", "mercadolivre", "mercado*", "magalu", "lojas americanas", 
        "barbearia", "don capi", "amazon", "tudao tech", "roupa", "calcado", "fiori"
    ]
}

CATEGORIAS_PADRAO = [
    "Supermercado",
    "Lazer",
    "Carro",
    "Assinaturas & Serviços",
    "Farmácia e Saúde",
    "Compras",
    "Outros"
]

def limpar_nome_base(descricao: str) -> str:
    """
    Remove marcações de parcelas como '01/10', '(2/5)', ' - Parcela 3'
    para permitir correspondência exata do estabelecimento.
    """
    padrao = r'(\s*[\(\[\-]?\s*\d+\s*[\/\-]\s*\d+\s*[\)\]]?|\s*-\s*parcela\s*\d+)'
    descricao_limpa = re.sub(padrao, '', descricao, flags=re.IGNORECASE)
    return descricao_limpa.strip()

def extrair_parcelas(descricao: str):
    padrao = r'(\d{1,2})\s*[\/\-]\s*(\d{1,2})'
    match = re.search(padrao, descricao)
    if match:
        atual = int(match.group(1))
        total = int(match.group(2))
        if 1 <= atual <= total:
            return atual, total
    return 1, 1

def calcular_fatura_mes(data_transacao: datetime, dia_fechamento: int = 11) -> str:
    if data_transacao.day >= dia_fechamento:
        data_fatura = data_transacao + relativedelta(months=1)
    else:
        data_fatura = data_transacao
    return data_fatura.strftime("%Y-%m")

def identificar_categoria(descricao: str, mapa_categorias: dict, id_padrao: int, session=None, user_id=None) -> int:
    """
    1. Verifica no histórico de transações do próprio usuário se já existe 
       uma compra anterior com o mesmo nome base classificada manualmente.
    2. Caso não exista histórico, recorre ao dicionário fixo REGRAS_CATEGORIAS.
    3. Caso não encontre em nenhuma das regras, atribui 'Outros'.
    """
    nome_base = limpar_nome_base(descricao)

    # 1. Busca memória histórica no banco
    if session and user_id:
        transacao_historico = session.query(Transacao).filter(
            Transacao.user_id == user_id,
            Transacao.descricao.ilike(f"%{nome_base}%")
        ).order_by(Transacao.data.desc(), Transacao.id.desc()).first()

        if transacao_historico and transacao_historico.categoria_id:
            return transacao_historico.categoria_id

    # 2. Busca por palavras-chave pré-definidas
    desc_normalizada = descricao.lower()
    for cat_nome, termos in REGRAS_CATEGORIAS.items():
        for termo in termos:
            if termo in desc_normalizada:
                if cat_nome in mapa_categorias:
                    return mapa_categorias[cat_nome]

    # 3. Fallback para 'Outros'
    return id_padrao

def importar_fatura_ofx(conteudo_bytes: bytes, nome_cartao: str = "Nubank", user_id: int = None) -> int:
    ofx_file = io.BytesIO(conteudo_bytes)
    ofx = OfxParser.parse(ofx_file)
    
    session = SessionLocal()
    
    try:
        # Garante o cartão
        cartao = session.query(Cartao).filter_by(nome=nome_cartao).first()
        if not cartao:
            cartao = Cartao(nome=nome_cartao)
            session.add(cartao)
            session.flush()

        # Garante as categorias mínimas no banco
        cats_existentes = {c.nome: c for c in session.query(Categoria).all()}
        for cat_nome in CATEGORIAS_PADRAO:
            if cat_nome not in cats_existentes:
                session.add(Categoria(nome=cat_nome))
        session.commit()

        # Mapa em memória {nome: id}
        todas_cats = session.query(Categoria).all()
        mapa_cats = {c.nome: c.id for c in todas_cats}
        id_outros = mapa_cats.get("Outros")

        total_importadas = 0

        for conta in ofx.accounts:
            for t in conta.statement.transactions:
                # Ignora créditos/pagamentos de fatura
                if float(t.amount) >= 0:
                    continue

                valor = round(abs(float(t.amount)), 2)
                data_pura = t.date.date() if hasattr(t.date, "date") else t.date
                descricao = t.memo.strip() if t.memo else (t.payee.strip() if t.payee else "Transação sem descrição")
                
                session.flush()

                # Trava contra duplicatas
                duplicada = session.query(Transacao).filter(
                    Transacao.user_id == user_id,
                    Transacao.data == data_pura,
                    Transacao.descricao == descricao,
                    Transacao.valor == valor
                ).first()

                if duplicada:
                    continue

                parcela_atual, total_parcelas = extrair_parcelas(descricao)
                fatura_mes = calcular_fatura_mes(t.date)

                # Prioriza a memória histórica da sua conta
                categoria_id = identificar_categoria(
                    descricao=descricao, 
                    mapa_categorias=mapa_cats, 
                    id_padrao=id_outros, 
                    session=session, 
                    user_id=user_id
                )

                nova_transacao = Transacao(
                    user_id=user_id,
                    cartao_id=cartao.id,
                    categoria_id=categoria_id,
                    data=data_pura,
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
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
    
    return total_importadas