import io
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from ofxparse import OfxParser
from database import SessionLocal, Transacao, Cartao, Categoria

# Mapeamento simplificado com as 7 categorias solicitadas
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

def identificar_categoria(descricao: str, mapa_categorias: dict, id_padrao: int) -> int:
    """
    Analisa o texto da transação e retorna o ID da categoria correspondente
    com base nas palavras-chave configuradas.
    """
    desc_normalizada = descricao.lower()
    for cat_nome, termos in REGRAS_CATEGORIAS.items():
        for termo in termos:
            if termo in desc_normalizada:
                if cat_nome in mapa_categorias:
                    return mapa_categorias[cat_nome]
    return id_padrao

def importar_fatura_ofx(conteudo_bytes: bytes, nome_cartao: str = "Nubank", user_id: int = None) -> int:
    """
    Analisa o ficheiro OFX, autoclassifica categorias e persiste as transações
    no PostgreSQL vinculadas ao user_id, evitando duplicatas e pagamentos de fatura.
    """
    ofx_file = io.BytesIO(conteudo_bytes)
    ofx = OfxParser.parse(ofx_file)
    
    session = SessionLocal()
    
    try:
        # 1. Garante a existência do cartão
        cartao = session.query(Cartao).filter_by(nome=nome_cartao).first()
        if not cartao:
            cartao = Cartao(nome=nome_cartao)
            session.add(cartao)
            session.flush()

        # 2. Assegura que todas as categorias padrão existem no banco
        cats_existentes = {c.nome: c for c in session.query(Categoria).all()}
        for cat_nome in CATEGORIAS_PADRAO:
            if cat_nome not in cats_existentes:
                nova_cat = Categoria(nome=cat_nome)
                session.add(nova_cat)
        session.commit()

        # 3. Recarrega mapa de categorias {nome: id}
        todas_cats = session.query(Categoria).all()
        mapa_cats = {c.nome: c.id for c in todas_cats}
        id_outros = mapa_cats.get("Outros")

        total_importadas = 0

        for conta in ofx.accounts:
            for t in conta.statement.transactions:
                # Ignora créditos/pagamentos de fatura (evita somar como despesa)
                if float(t.amount) >= 0:
                    continue

                valor = round(abs(float(t.amount)), 2)
                
                # Normaliza data e descrição
                data_pura = t.date.date() if hasattr(t.date, "date") else t.date
                descricao = t.memo.strip() if t.memo else (t.payee.strip() if t.payee else "Transação sem descrição")
                
                session.flush()

                # Prevenção contra duplicatas no banco
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

                # Identificação inteligente de categoria
                categoria_id = identificar_categoria(descricao, mapa_cats, id_outros)

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