# 💳 Personal Finance Dashboard

Dashboard financeiro moderno construído com **Streamlit**, **Python** e **SQLAlchemy**. O projeto foi desenhado para quem precisa de clareza real sobre gastos no cartão de crédito, divisão inteligente de despesas com terceiros, controle de parcelamentos futuros e gestão de contas fixas recorrentes.

---

## 🚀 Funcionalidades

- **Importação Direta de Faturas (.OFX):** Leitura de extratos bancários com prevenção nativa contra duplicidade de transações.
- **Ciclo de Fechamento Inteligente:** Separação automática das compras para a fatura correta com base no dia de fechamento (padrão: dia 11).
- **Divisão de Compras & Herança de Parcelamentos:**
  - Marque compras que pertencem a outra pessoa (ex: dependente/mãe).
  - Propagação automática: ao marcar uma compra parcelada, todas as parcelas futuras dessa mesma compra já são atribuídas à pessoa nas próximas faturas importadas.
- **Projeção Futura Mês a Mês:**
  - Gráficos e tabelas detalhadas do valor pré-comprometido em parcelas futuras.
  - Visualização isolada para os seus gastos vs. gastos de terceiros a receber.
- **Despesas Fixas & Saldo Líquido Real:**
  - Cadastro de contas recorrentes (aluguel, academia, serviços).
  - Cálculo instantâneo do saldo livre real do mês (`Renda - (Sua Fatura + Despesas Fixas)`).
- **Categorização Personalizada:** Crie novas categorias na barra lateral e reclassifique qualquer transação diretamente na tabela com um clique.
- **Persistência Total:** Guarda suas preferências e renda mensal automaticamente.
- **Design Glassmorphism:** Interface limpa com tema escuro, tipografia refinada e cards responsivos.

---

## 🛠️ Tecnologias

- **Linguagem:** Python 3.10+
- **Interface:** [Streamlit](https://streamlit.io/)
- **Visualização de Dados:** [Plotly Express](https://plotly.com/python/)
- **Manipulação de Dados:** [Pandas](https://pandas.pydata.org/)
- **Modelagem & Banco de Dados:** [SQLAlchemy](https://www.sqlalchemy.org/)
- **Drivers de Banco:** SQLite (padrão local) e PostgreSQL via `psycopg2-binary` (nuvem)
- **Parser de Extratos:** [OfxParser](https://github.com/jbmoelker/ofxparse)

---

## 📂 Estrutura do Projeto

```text
├── .streamlit/
│   └── config.toml          # Customização visual e paleta de cores (Dark theme)
├── app.py                   # Interface principal do Streamlit e lógica de visualização
├── database.py              # Definição dos modelos ORM e conexão dinâmica (Local/Nuvem)
├── importador.py            # Parser OFX, regex de parcelas e motor de categorização
├── requirements.txt         # Dependências do projeto
├── .gitignore               # Proteção para nunca versionar arquivos .db ou extratos .ofx
└── README.md                # Documentação
