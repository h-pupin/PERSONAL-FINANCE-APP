import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from dateutil.relativedelta import relativedelta
from database import SessionLocal, Transacao, Categoria, Cartao, DespesaFixa, Configuracao
from importador import importar_fatura_ofx, limpar_nome_base
import tempfile
import os

st.set_page_config(
    page_title="Finanças Pessoais", 
    page_icon="💳", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS Moderna
st.markdown("""
<style>
    /* Estilo geral e fontes */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Cards métricos customizados */
    .metric-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        backdrop-filter: blur(10px);
        margin-bottom: 12px;
    }
    .metric-title {
        color: #94a3b8;
        font-size: 0.85rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }
    .metric-value {
        color: #f8fafc;
        font-size: 1.55rem;
        font-weight: 700;
    }
    .metric-positive {
        color: #34d399 !important;
    }
    .metric-negative {
        color: #f87171 !important;
    }
    .metric-sub {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 4px;
    }
    
    /* Abas personalizadas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 44px;
        border-radius: 8px;
        padding: 0 18px;
        font-weight: 500;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(139, 92, 246, 0.15) !important;
        color: #a78bfa !important;
    }
</style>
""", unsafe_allow_html=True)

def obter_saldo_salvo() -> float:
    session = SessionLocal()
    config = session.query(Configuracao).filter_by(chave="saldo_mensal").first()
    session.close()
    if config:
        try:
            return float(config.valor)
        except ValueError:
            return 5000.0
    return 5000.0

def salvar_saldo(novo_saldo: float):
    session = SessionLocal()
    config = session.query(Configuracao).filter_by(chave="saldo_mensal").first()
    if not config:
        config = Configuracao(chave="saldo_mensal", valor=str(novo_saldo))
        session.add(config)
    else:
        config.valor = str(novo_saldo)
    session.commit()
    session.close()

def carregar_categorias():
    session = SessionLocal()
    cats = session.query(Categoria).order_by(Categoria.nome).all()
    lista_cats = [c.nome for c in cats]
    session.close()
    return lista_cats

def carregar_transacoes():
    session = SessionLocal()
    query = session.query(
        Transacao.id,
        Transacao.data,
        Transacao.descricao,
        Transacao.valor,
        Transacao.fatura_mes,
        Transacao.parcela_atual,
        Transacao.total_parcelas,
        Transacao.da_mae,
        Categoria.nome.label("categoria"),
        Cartao.nome.label("cartao")
    ).join(Categoria, Transacao.categoria_id == Categoria.id, isouter=True)\
     .join(Cartao, Transacao.cartao_id == Cartao.id, isouter=True)
    
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    if not df.empty:
        df['data'] = pd.to_datetime(df['data'])
    return df

def carregar_despesas_fixas():
    session = SessionLocal()
    df = pd.read_sql(session.query(DespesaFixa).statement, session.bind)
    session.close()
    return df

st.title("💳 Gestão Financeira Pessoal")

# Sidebar
st.sidebar.header("⚙️ Configurações & Saldo")

saldo_banco = obter_saldo_salvo()
saldo_informado = st.sidebar.number_input(
    "Seu Saldo / Renda do Mês (R$)",
    min_value=0.0,
    value=saldo_banco,
    step=100.0
)

if saldo_informado != saldo_banco:
    salvar_saldo(saldo_informado)

st.sidebar.markdown("---")
st.sidebar.subheader("🏷️ Categorias")
with st.sidebar.expander("Cadastrar Nova Categoria"):
    with st.form("form_nova_cat", clear_on_submit=True):
        nova_cat_nome = st.text_input("Nome da Categoria", placeholder="Ex: Farmácia, Carro...")
        sub_cat = st.form_submit_button("Salvar")
        if sub_cat and nova_cat_nome:
            session = SessionLocal()
            existente = session.query(Categoria).filter_by(nome=nova_cat_nome.strip()).first()
            if not existente:
                session.add(Categoria(nome=nova_cat_nome.strip()))
                session.commit()
                st.sidebar.success(f"Categoria criada!")
            else:
                st.sidebar.warning("Categoria já existe!")
            session.close()
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📁 Importar Fatura")
uploaded_file = st.sidebar.file_uploader("Subir Fatura (.ofx)", type=["ofx"], key="uploader_ofx")
if uploaded_file is not None:
    conteudo_bytes = uploaded_file.getvalue()
    qtd_importadas = importar_fatura_ofx(conteudo_bytes, nome_cartao="Nubank")
    if qtd_importadas > 0:
        st.sidebar.success(f"{qtd_importadas} transações importadas!")
        st.rerun()
    else:
        st.sidebar.info("Nenhuma transação nova encontrada nesta fatura.")

df = carregar_transacoes()
df_fixas = carregar_despesas_fixas()
lista_categorias_disponiveis = carregar_categorias()

total_fixas = df_fixas[df_fixas['ativa'] == True]['valor'].sum() if not df_fixas.empty else 0.0

if df.empty:
    st.info("Nenhuma transação encontrada no banco de dados. Faça o upload de uma fatura OFX.")
    st.stop()

# Filtros
faturas_disponiveis = sorted(list(df['fatura_mes'].dropna().unique()), reverse=True)
fatura_sel = st.sidebar.selectbox("Fatura Selecionada (Vencimento)", faturas_disponiveis)

cartoes = ["Todos"] + sorted(list(df['cartao'].dropna().unique()))
cartao_sel = st.sidebar.selectbox("Cartão", cartoes)

df_fatura = df[df['fatura_mes'] == fatura_sel].copy()
if cartao_sel != "Todos":
    df_fatura = df_fatura[df_fatura['cartao'] == cartao_sel]

df_henrique = df_fatura[df_fatura['da_mae'] == False]
df_mae = df_fatura[df_fatura['da_mae'] == True]

total_fatura_geral = df_fatura['valor'].sum()
total_henrique = df_henrique['valor'].sum()
total_mae = df_mae['valor'].sum()

total_comprometido_mes = total_henrique + total_fixas
saldo_restante_henrique = saldo_informado - total_comprometido_mes

# Cards Modernos no Topo
def format_reais(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Renda / Saldo</div>
        <div class="metric-value">{format_reais(saldo_informado)}</div>
        <div class="metric-sub">Base mensal cadastrada</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Sua Fatura</div>
        <div class="metric-value">{format_reais(total_henrique)}</div>
        <div class="metric-sub">{len(df_henrique)} compras suas</div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Despesas Fixas</div>
        <div class="metric-value">{format_reais(total_fixas)}</div>
        <div class="metric-sub">Contas recorrentes ativas</div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Parte da Mãe</div>
        <div class="metric-value">{format_reais(total_mae)}</div>
        <div class="metric-sub">Total a receber/abater</div>
    </div>
    """, unsafe_allow_html=True)

saldo_class = "metric-positive" if saldo_restante_henrique >= 0 else "metric-negative"
pct_livre = ((saldo_restante_henrique / saldo_informado) * 100) if saldo_informado > 0 else 0

with c5:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Saldo Livre Real</div>
        <div class="metric-value {saldo_class}">{format_reais(saldo_restante_henrique)}</div>
        <div class="metric-sub">{pct_livre:.1f}% do saldo total livre</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

# Abas de Gestão
tab_painel, tab_gerenciar, tab_projecoes, tab_fixas, tab_mae = st.tabs([
    "📊 Visão Geral", 
    "✍️ Editar / Categorizar", 
    "🔮 Parcelas Futuras", 
    "📌 Despesas Fixas", 
    "👩‍👧 Extrato da Mãe"
])

# Paleta refinada para gráficos
CORES_CHART = ["#8b5cf6", "#3b82f6", "#10b981", "#f59e0b", "#ec4899", "#6366f1", "#14b8a6"]

# ABA: VISÃO GERAL
with tab_painel:
    g1, g2 = st.columns([3, 2])
    with g1:
        st.subheader(f"Evolução Diária de Gastos ({fatura_sel})")
        df_dia = df_henrique.groupby(df_henrique['data'].dt.date)['valor'].sum().reset_index()
        fig_linha = px.line(
            df_dia, 
            x='data', 
            y='valor', 
            markers=True, 
            labels={'data': 'Data', 'valor': 'Valor (R$)'},
            template="plotly_dark"
        )
        fig_linha.update_traces(line_color='#8b5cf6', marker=dict(size=8, color='#a78bfa'))
        fig_linha.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=10, r=10, t=30, b=10)
        )
        st.plotly_chart(fig_linha, use_container_width=True)

    with g2:
        st.subheader("Categorias de Gasto")
        df_cat = df_henrique.groupby('categoria')['valor'].sum().reset_index()
        fig_pizza = px.pie(
            df_cat, 
            names='categoria', 
            values='valor', 
            hole=0.55,
            color_discrete_sequence=CORES_CHART,
            template="plotly_dark"
        )
        fig_pizza.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=10, r=10, t=30, b=10)
        )
        st.plotly_chart(fig_pizza, use_container_width=True)

    st.markdown("---")
    st.subheader("Suas Transações Nesta Fatura")
    df_henrique_exibir = df_henrique[['data', 'descricao', 'categoria', 'parcela_atual', 'total_parcelas', 'valor']].copy()
    df_henrique_exibir['data'] = df_henrique_exibir['data'].dt.strftime('%d/%m/%Y')
    df_henrique_exibir['parcela'] = df_henrique_exibir['parcela_atual'].astype(str) + "/" + df_henrique_exibir['total_parcelas'].astype(str)
    df_henrique_exibir['valor'] = df_henrique_exibir['valor'].apply(format_reais)
    st.dataframe(df_henrique_exibir.drop(columns=['parcela_atual', 'total_parcelas']), use_container_width=True)

# ABA: EDITAR CATEGORIAS E ATRIBUIR COMPRAS DA MÃE
with tab_gerenciar:
    st.subheader(f"Gerenciar Transações da Fatura {fatura_sel}")
    st.caption("Reclassifique categorias e vincule compras parceladas da sua mãe com persistência automática.")

    editor_df = df_fatura[['id', 'da_mae', 'data', 'descricao', 'categoria', 'valor']].copy()
    editor_df['data'] = editor_df['data'].dt.strftime('%d/%m/%Y')
    opcoes_categorias = sorted(list(set(lista_categorias_disponiveis + editor_df['categoria'].dropna().tolist())))

    colunas_config = {
        "id": None,
        "da_mae": st.column_config.CheckboxColumn("Compra da Mãe?", default=False),
        "data": st.column_config.TextColumn("Data", disabled=True),
        "descricao": st.column_config.TextColumn("Descrição", disabled=True),
        "categoria": st.column_config.SelectboxColumn("Categoria", options=opcoes_categorias, required=True),
        "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", disabled=True)
    }

    tabela_editada = st.data_editor(
        editor_df,
        column_config=colunas_config,
        hide_index=True,
        use_container_width=True,
        key="editor_transacoes_full"
    )

    if st.button("💾 Salvar Alterações de Categorias e Titularidade"):
        session = SessionLocal()
        mapa_cats = {c.nome: c.id for c in session.query(Categoria).all()}
        
        for idx, row in tabela_editada.iterrows():
            t_id = int(row['id'])
            novo_status_mae = bool(row['da_mae'])
            nome_categoria = str(row['categoria'])
            
            if nome_categoria not in mapa_cats:
                nova_entidade = Categoria(nome=nome_categoria)
                session.add(nova_entidade)
                session.flush()
                mapa_cats[nome_categoria] = nova_entidade.id
            
            cat_id = mapa_cats[nome_categoria]

            t_atual = session.query(Transacao).filter(Transacao.id == t_id).first()
            if t_atual:
                t_atual.da_mae = novo_status_mae
                t_atual.categoria_id = cat_id
                
                if t_atual.total_parcelas > 1:
                    nome_limpo = limpar_nome_base(t_atual.descricao)
                    todas_parceladas = session.query(Transacao).filter(Transacao.total_parcelas > 1).all()
                    for tp in todas_parceladas:
                        if limpar_nome_base(tp.descricao) == nome_limpo:
                            tp.da_mae = novo_status_mae

        session.commit()
        session.close()
        st.success("Alterações salvas!")
        st.rerun()

# ABA: PARCELAS FUTURAS
with tab_projecoes:
    st.subheader("🔮 Parcelas Futuras Mês a Mês")
    
    tipo_visao = st.radio("Visualizar parcelamentos futuros de:", ["Seus Gastos", "Gastos da Mãe"], horizontal=True)
    df_alvo = df[df['da_mae'] == False] if tipo_visao == "Seus Gastos" else df[df['da_mae'] == True]
    
    df_parcelados = df_alvo[df_alvo['total_parcelas'] > 1].copy()
    projecoes = []

    if not df_parcelados.empty:
        for desc_grupo, grupo in df_parcelados.groupby(df_parcelados['descricao'].apply(limpar_nome_base)):
            ultimo_reg = grupo.sort_values('parcela_atual', ascending=False).iloc[0]
            parcelas_restantes = int(ultimo_reg['total_parcelas'] - ultimo_reg['parcela_atual'])
            data_base = ultimo_reg['data']
            
            for i in range(1, parcelas_restantes + 1):
                mes_futuro = data_base + relativedelta(months=i)
                fatura_futura = (mes_futuro + relativedelta(months=1)) if mes_futuro.day >= 11 else mes_futuro
                projecoes.append({
                    "fatura_destino": fatura_futura.strftime("%Y-%m"),
                    "descricao": ultimo_reg['descricao'],
                    "parcela_projetada": f"{int(ultimo_reg['parcela_atual']) + i}/{int(ultimo_reg['total_parcelas'])}",
                    "categoria": ultimo_reg['categoria'],
                    "valor": float(ultimo_reg['valor'])
                })

    if projecoes:
        df_proj = pd.DataFrame(projecoes)
        df_proj_agrupado = df_proj.groupby("fatura_destino")['valor'].sum().reset_index().sort_values("fatura_destino")

        col_proj1, col_proj2 = st.columns([3, 2])
        with col_proj1:
            fig_bar = px.bar(
                df_proj_agrupado,
                x="fatura_destino",
                y="valor",
                text="valor",
                labels={"fatura_destino": "Fatura Futura", "valor": "Total Comprometido (R$)"},
                title=f"Total Comprometido ({tipo_visao})",
                template="plotly_dark"
            )
            fig_bar.update_traces(marker_color='#8b5cf6', texttemplate='R$ %{y:,.2f}', textposition='outside')
            fig_bar.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=10, r=10, t=30, b=10)
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_proj2:
            st.write(f"**Detalhes das Parcelas ({tipo_visao})**")
            faturas_futuras_opcoes = ["Todas"] + sorted(list(df_proj['fatura_destino'].unique()))
            fatura_futura_sel = st.selectbox("Selecione o mês para inspecionar:", faturas_futuras_opcoes, key="sel_fut_mae")
            
            df_detalhe_proj = df_proj if fatura_futura_sel == "Todas" else df_proj[df_proj['fatura_destino'] == fatura_futura_sel]
            
            df_detalhe_exibir = df_detalhe_proj[['fatura_destino', 'descricao', 'parcela_projetada', 'categoria', 'valor']].copy()
            df_detalhe_exibir.rename(columns={
                'fatura_destino': 'Fatura',
                'descricao': 'Compra',
                'parcela_projetada': 'Parcela',
                'categoria': 'Categoria',
                'valor': 'Valor'
            }, inplace=True)
            df_detalhe_exibir['Valor'] = df_detalhe_exibir['Valor'].apply(format_reais)
            st.dataframe(df_detalhe_exibir, use_container_width=True, height=280)
    else:
        st.info(f"Nenhum parcelamento futuro ativo para: {tipo_visao}.")

# ABA: DESPESAS FIXAS
with tab_fixas:
    st.subheader("📌 Cadastro de Despesas Fixas")
    col_fix1, col_fix2 = st.columns([1, 2])
    
    with col_fix1:
        with st.form("form_nova_fixa", clear_on_submit=True):
            st.write("**Nova Despesa Fixa**")
            nome_fixa = st.text_input("Nome da Despesa", placeholder="Ex: Aluguel")
            valor_fixa = st.number_input("Valor Mensal (R$)", min_value=0.0, step=10.0)
            categoria_fixa = st.text_input("Categoria", value="Moradia")
            submit_fixa = st.form_submit_button("Adicionar Despesa")
            
            if submit_fixa and nome_fixa and valor_fixa > 0:
                session = SessionLocal()
                nova = DespesaFixa(nome=nome_fixa, valor=valor_fixa, categoria=categoria_fixa, ativa=True)
                session.add(nova)
                session.commit()
                session.close()
                st.success(f"Despesa cadastrada!")
                st.rerun()

    with col_fix2:
        st.write("**Despesas Cadastradas**")
        if not df_fixas.empty:
            df_fixas_editor = df_fixas[['id', 'ativa', 'nome', 'categoria', 'valor']].copy()
            config_fixas = {
                "id": None,
                "ativa": st.column_config.CheckboxColumn("Ativa?", default=True),
                "nome": st.column_config.TextColumn("Despesa"),
                "categoria": st.column_config.TextColumn("Categoria"),
                "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")
            }
            editadas_fixas = st.data_editor(df_fixas_editor, column_config=config_fixas, hide_index=True, use_container_width=True)
            
            if st.button("💾 Atualizar Despesas Fixas"):
                session = SessionLocal()
                for _, row in editadas_fixas.iterrows():
                    session.query(DespesaFixa).filter(DespesaFixa.id == int(row['id'])).update({
                        "ativa": bool(row['ativa']),
                        "nome": str(row['nome']),
                        "categoria": str(row['categoria']),
                        "valor": float(row['valor'])
                    })
                session.commit()
                session.close()
                st.success("Despesas fixas atualizadas!")
                st.rerun()
        else:
            st.info("Nenhuma despesa fixa cadastrada ainda.")

# ABA: EXTRATO DA MÃE
with tab_mae:
    st.subheader(f"Gastos da Mãe - Fatura {fatura_sel}")
    st.metric("Total a Receber nesta fatura", format_reais(total_mae))
    if not df_mae.empty:
        df_mae_exibir = df_mae[['data', 'descricao', 'categoria', 'parcela_atual', 'total_parcelas', 'valor']].copy()
        df_mae_exibir['data'] = df_mae_exibir['data'].dt.strftime('%d/%m/%Y')
        df_mae_exibir['parcela'] = df_mae_exibir['parcela_atual'].astype(str) + "/" + df_mae_exibir['total_parcelas'].astype(str)
        df_mae_exibir['valor'] = df_mae_exibir['valor'].apply(format_reais)
        st.dataframe(df_mae_exibir.drop(columns=['parcela_atual', 'total_parcelas']), use_container_width=True)
    else:
        st.info("Nenhuma compra atribuída a ela nesta fatura.")