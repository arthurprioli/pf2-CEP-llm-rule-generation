import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import HTTPError, RequestException
from app.siddhi_client import deploy_regra_siddhi, remover_regra_siddhi

# ==========================================
# TESTES DE DEPLOY (PUSH DA REGRA)
# ==========================================


@patch("app.siddhi_client.requests.post")
def test_deploy_regra_siddhi_sucesso(mock_post):
    """Valida se o cliente envia a requisição corretamente e lida com o sucesso."""
    # Configura o mock para simular uma resposta de sucesso do Siddhi
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    id_regra = "123e4567-e89b-12d3-a456-426614174000"
    payload = "define stream FluxoEntrada (dado string);"

    resultado = deploy_regra_siddhi(id_regra, payload)

    # Asserções
    assert resultado is True
    mock_post.assert_called_once()

    # Valida se o cliente injetou o @App:name e substituiu os hifens por underscores
    argumentos_enviados = mock_post.call_args.kwargs["data"]
    assert (
        "@App:name('Regra_123e4567_e89b_12d3_a456_426614174000')" in argumentos_enviados
    )
    assert payload in argumentos_enviados


@patch("app.siddhi_client.requests.post")
def test_deploy_regra_siddhi_com_app_name_existente(mock_post):
    """Valida se o cliente respeita um @App:name caso a regra já o possua."""
    mock_response = MagicMock()
    mock_post.return_value = mock_response

    id_regra = "123e4567-e89b-12d3-a456-426614174000"
    payload = (
        "@App:name('MinhaRegraCustomizada')\ndefine stream FluxoEntrada (dado string);"
    )

    deploy_regra_siddhi(id_regra, payload)

    # Valida se o cliente NÃO injetou um segundo @App:name
    argumentos_enviados = mock_post.call_args.kwargs["data"]
    assert argumentos_enviados.count("@App:name") == 1
    assert "Regra_123e" not in argumentos_enviados


@patch("app.siddhi_client.requests.post")
def test_deploy_regra_siddhi_falha_sintaxe(mock_post):
    """Valida se o cliente trata corretamente erros 400 Bad Request do Siddhi."""
    # Simula o disparo de uma exceção HTTP (como se o Siddhi rejeitasse a sintaxe)
    mock_response = MagicMock()
    mock_response.text = "SiddhiQL syntax error"
    mock_erro = HTTPError("400 Client Error: Bad Request")
    mock_erro.response = mock_response

    mock_post.return_value.raise_for_status.side_effect = mock_erro

    resultado = deploy_regra_siddhi("uuid-qualquer", "regra quebrada")

    assert resultado is False


# ==========================================
# TESTES DE REMOÇÃO (DELETE DA REGRA)
# ==========================================


@patch("app.siddhi_client.requests.delete")
def test_remover_regra_siddhi_sucesso(mock_delete):
    """Valida se o comando de inativação é formatado e enviado corretamente."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_delete.return_value = mock_response

    id_regra = "1111-2222-3333-4444"
    resultado = remover_regra_siddhi(id_regra)

    assert resultado is True
    mock_delete.assert_called_once()

    # Verifica se a URL foi construída corretamente com o nome da regra convertido
    url_chamada = mock_delete.call_args.args[0]
    assert url_chamada.endswith("/Regra_1111_2222_3333_4444")


@patch("app.siddhi_client.requests.delete")
def test_remover_regra_siddhi_falha_conexao(mock_delete):
    """Valida se a aplicação sobrevive caso o Siddhi esteja offline durante a remoção."""
    mock_delete.side_effect = RequestException("Connection Refused")

    resultado = remover_regra_siddhi("uuid-qualquer")

    # A função deve capturar a exceção e retornar False de forma graciosa
    assert resultado is False
