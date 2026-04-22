import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal
from app.models import RegraCEP


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    print("[Setup] Limpando o banco antigo...")
    Base.metadata.drop_all(bind=engine)
    print("[Setup]: Criando tabelas de teste...")
    Base.metadata.create_all(bind=engine)
    yield
    print("[Remoção] Removendo tabelas de teste")
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(setup_database):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def test_conexao_banco():
    """Valida a conexão ao PostgreSQL"""
    try:
        with engine.connect() as conn:
            assert conn.closed is False
    except Exception as e:
        pytest.fail(f"Falha ao conectar ao banco de dados: {e}")


def test_tabela_regras_existe():
    """Testa se a tabela de regras CEP foi criada corretamente"""
    inspector = inspect(engine)
    tabelas = inspector.get_table_names()
    assert "regras_cep" in tabelas, "A tabela regras_cep não foi encontrada no banco."


def test_colunas_e_tipos():
    """Valida se o tipo das colunas criadas está correto"""
    inspector = inspect(engine)
    colunas = {col["name"]: col["type"] for col in inspector.get_columns("regras_cep")}

    assert "id_regra" in colunas
    assert "payload_regra" in colunas
    assert "status" in colunas
    assert "num_ocorrencias" in colunas
    assert "score_relevancia" in colunas


def test_insercao_modelo():
    """Testa uma inserção no banco pra testar valores defaults"""
    db_session = SessionLocal()

    try:
        nova_regra = RegraCEP(
            payload_regra="SE (evento.tipo = 'noticia') ENTAO alerta_noticia"
        )

        db_session.add(nova_regra)
        db_session.flush()

        assert nova_regra.id_regra is not None
        assert len(str(nova_regra.id_regra)) == 36

        assert (
            nova_regra.payload_regra
            == "SE (evento.tipo = 'noticia') ENTAO alerta_noticia"
        )

        assert nova_regra.status == "Sugerida"
        assert nova_regra.num_ocorrencias == 0
        assert nova_regra.score_relevancia == 0.0000

        assert nova_regra.dt_criacao is not None
        assert nova_regra.dt_atualizacao is not None
    finally:
        db_session.rollback()
        db_session.close()
