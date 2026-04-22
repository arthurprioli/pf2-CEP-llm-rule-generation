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
    response_criacao = client.post("/regras/manual", json={"payload_regra": "Regra de Hot Swap"})
    id_regra = response_criacao.json()["id_regra"]

    payload_update = {"status": "Aprovada"}
    response_update = client.put(f"/regras/{id_regra}/status", json=payload_update)

    assert response_update.status_code == 200
    data_update = response_update.json()
    assert data_update["status"] == "Aprovada"

def test_atualizar_status_invalido():
    """Valida a barreira do Pydantic contra dados corrompidos."""
    response_criacao = client.post("/regras/manual", json={"payload_regra": "Regra Corrompida"})
    id_regra = response_criacao.json()["id_regra"]

    payload_update = {"status": "StatusInexistente"}
    response_update = client.put(f"/regras/{id_regra}/status", json=payload_update)

    assert response_update.status_code == 422
    erro_detalhe = response_update.json()["detail"][0]["msg"]
    assert "String should match pattern" in erro_detalhe