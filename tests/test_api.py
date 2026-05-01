import uuid

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, engine, Base, SessionLocal

Base.metadata.create_all(bind=engine)


def override_get_db():
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# ==========================================
# CASOS DE TESTE
# ==========================================


def test_criar_regra_manual():
    """Valida se o endpoint POST /regras/manual cria a regra corretamente e retorna 201."""
    payload = {"payload_regra": "SE (ip = '127.0.0.1') ENTAO bloquear"}

    response = client.post("/regras/manual", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["payload_regra"] == payload["payload_regra"]
    assert data["status"] == "Manual"
    assert "id_regra" in data


def test_listar_regras():
    client.post("/regras/manual", json={"payload_regra": "Regra para listagem"})

    response = client.get("/regras")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id_regra" in data[0]


def test_atualizar_status_valido():
    response_criacao = client.post(
        "/regras/manual", json={"payload_regra": "Regra de Hot Swap"}
    )
    id_regra = response_criacao.json()["id_regra"]

    payload_update = {"status": "Aprovada"}
    response_update = client.put(f"/regras/{id_regra}/status", json=payload_update)

    assert response_update.status_code == 200
    data_update = response_update.json()
    assert data_update["status"] == "Aprovada"


def test_atualizar_status_invalido():
    """Valida a barreira do Pydantic contra dados corrompidos."""
    response_criacao = client.post(
        "/regras/manual", json={"payload_regra": "Regra Corrompida"}
    )
    id_regra = response_criacao.json()["id_regra"]

    payload_update = {"status": "StatusInexistente"}
    response_update = client.put(f"/regras/{id_regra}/status", json=payload_update)

    assert response_update.status_code == 422
    erro_detalhe = response_update.json()["detail"][0]["msg"]
    assert "String should match pattern" in erro_detalhe


def test_registrar_match_sucesso():
    """Valida se o webhook incrementa o número de ocorrências de uma regra existente."""
    # Create a rule for testing
    response_criacao = client.post(
        "/regras/manual", json={"payload_regra": "Regra para Teste de Match"}
    )
    assert response_criacao.status_code == 201
    id_regra = response_criacao.json()["id_regra"]
    ocorrencias_iniciais = response_criacao.json()["num_ocorrencias"]

    payload_match = {"id_regra": id_regra, "alerta": "Padrão detectado pelo motor CEP"}
    response_match = client.post("/regras/matches", json=payload_match)

    assert response_match.status_code == 200
    assert response_match.json()["status"] == "Sucesso!"

    response_get = client.get("/regras")
    regra_atualizada = next(r for r in response_get.json() if r["id_regra"] == id_regra)

    assert regra_atualizada["num_ocorrencias"] == ocorrencias_iniciais + 1
    assert regra_atualizada["ultima_ocorrencia"] is not None


def test_registrar_match_regra_inexistente():
    """Valida se o webhook devolve 404 quando o Siddhi envia o alerta de uma regra que já foi apagada."""
    id_falso = str(uuid.uuid4())
    payload_match = {"id_regra": id_falso}

    response_match = client.post("/regras/matches", json=payload_match)

    assert response_match.status_code == 404
    assert "não encontrada" in response_match.json()["detail"]


def test_registrar_match_payload_invalido():
    """Valida se o Pydantic bloqueia alertas do Siddhi com formatação JSON quebrada (sem ID)."""
    payload_quebrado = {"alerta": "Faltou o ID da regra!"}

    response_match = client.post("/regras/matches", json=payload_quebrado)

    assert response_match.status_code == 422


def test_render_painel():
    """Valida se a página HTML é gerada e devolvida com sucesso pelo Jinja2."""

    client.post("/regras/manual", json={"payload_regra": "Regra para UI"})

    response = client.get("/painel")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    html_content = response.text
    assert "Orquestrador de Regras CEP" in html_content
    assert "Regra para UI" in html_content
