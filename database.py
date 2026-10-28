from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, 
    DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

class Cartao(Base):
    __tablename__ = 'cartoes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(50), nullable=False)
    fechamento_dia = Column(Integer, default=11)
    vencimento_dia = Column(Integer, default=19)

    transacoes = relationship('Transacao', back_populates='cartao')

class Categoria(Base):
    __tablename__ = 'categorias'

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(50), unique=True, nullable=False)

    transacoes = relationship('Transacao', back_populates='categoria')

class Transacao(Base):
    __tablename__ = 'transacoes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(DateTime, nullable=False)
    descricao = Column(String(150), nullable=False)
    valor = Column(Float, nullable=False)
    fatura_mes = Column(String(7), nullable=False)
    parcela_atual = Column(Integer, default=1)
    total_parcelas = Column(Integer, default=1)
    
    da_mae = Column(Boolean, default=False)
    
    cartao_id = Column(Integer, ForeignKey('cartoes.id'), nullable=True)
    categoria_id = Column(Integer, ForeignKey('categorias.id'), nullable=True)

    cartao = relationship('Cartao', back_populates='transacoes')
    categoria = relationship('Categoria', back_populates='transacoes')

class DespesaFixa(Base):
    __tablename__ = 'despesas_fixas'

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False)
    valor = Column(Float, nullable=False)
    categoria = Column(String(50), default="Contas Fixas")
    ativa = Column(Boolean, default=True)

# Tabela para salvar preferências e saldo configurado
class Configuracao(Base):
    __tablename__ = 'configuracoes'

    chave = Column(String(50), primary_key=True)
    valor = Column(String(100), nullable=False)

engine = create_engine('sqlite:///financas.db', echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

if __name__ == '__main__':
    print("Banco atualizado com tabela de configurações!")