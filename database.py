import os
import bcrypt
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, 
    Date, ForeignKey, text
)
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# 1. Captura da URL: prioriza st.secrets (Streamlit Cloud), depois os.getenv, depois SQLite local
DATABASE_URL = None
try:
    import streamlit as st
    if "DATABASE_URL" in st.secrets:
        DATABASE_URL = st.secrets["DATABASE_URL"]
except Exception:
    pass

if not DATABASE_URL:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///financas.db")

# 2. Criação única do engine com NullPool para gerenciar as conexões no Supabase
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    poolclass=NullPool
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    nome = Column(String(100), nullable=False)
    senha_hash = Column(String(255), nullable=False)

class Categoria(Base):
    __tablename__ = "categorias"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), unique=True, nullable=False)

class Cartao(Base):
    __tablename__ = "cartoes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), unique=True, nullable=False)

class Transacao(Base):
    __tablename__ = "transacoes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    data = Column(Date, nullable=False)
    descricao = Column(String(255), nullable=False)
    valor = Column(Float, nullable=False)
    fatura_mes = Column(String(7), nullable=False)
    parcela_atual = Column(Integer, default=1)
    total_parcelas = Column(Integer, default=1)
    da_mae = Column(Boolean, default=False)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=True)
    cartao_id = Column(Integer, ForeignKey("cartoes.id"), nullable=True)

class DespesaFixa(Base):
    __tablename__ = "despesas_fixas"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    nome = Column(String(100), nullable=False)
    valor = Column(Float, nullable=False)
    categoria = Column(String(100), nullable=False)
    ativa = Column(Boolean, default=True)

class Configuracao(Base):
    __tablename__ = "configuracoes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    chave = Column(String(50), nullable=False)
    valor = Column(String(255), nullable=False)

# Cria tabelas novas (como 'usuarios')
Base.metadata.create_all(bind=engine)

# Auto-migração: adiciona user_id nas tabelas existentes caso ainda não existam no Supabase
def executar_migracao_user_id():
    with engine.connect() as conn:
        for tabela in ["transacoes", "despesas_fixas", "configuracoes"]:
            try:
                conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS user_id INTEGER;"))
                conn.commit()
            except Exception:
                pass

executar_migracao_user_id()

# Funções de Autenticação
def criar_usuario(session, username, nome, senha):
    salt = bcrypt.gensalt()
    hash_senha = bcrypt.hashpw(senha.encode('utf-8'), salt).decode('utf-8')
    novo_user = Usuario(username=username.lower().strip(), nome=nome.strip(), senha_hash=hash_senha)
    session.add(novo_user)
    session.commit()
    return novo_user

def verificar_usuario(session, username, senha):
    user = session.query(Usuario).filter(Usuario.username == username.lower().strip()).first()
    if user and bcrypt.checkpw(senha.encode('utf-8'), user.senha_hash.encode('utf-8')):
        return user
    return None