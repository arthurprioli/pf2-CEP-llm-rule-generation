import requests
import os

SIDDHI_RUNNER_URL = os.getenv("SIDDHI_RUNNER_URL")


def deploy_regra_siddhi(id_regra: str, payload: str):
    """
    Faz um PUSH de uma regra no Siddhi.
    """
    app_name = f"Regra_{str(id_regra).replace('-', '_')}"

    if "@App:name" not in payload:
        siddhi_app_string = f"@App:name('{app_name}')\\n" + payload
    else:
        siddhi_app_string = payload

    headers = {"Content-Type": "text/plain"}

    try:
        resp = requests.post(SIDDHI_RUNNER_URL, data=siddhi_app_string, headers=headers)
        resp.raise_for_status()
        print(f"[SIDDHI] Regra {id_regra} implantada com sucesso no Siddhi Runner.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"[SIDDHI] Erro ao implantar regra {id_regra} no Siddhi Runner: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"[SIDDHI] Resposta do erro: {e.response.text}")
        return False


def remover_regra_siddhi(id_regra: str):
    """
    Remove uma regra do Siddhi com DELETE.
    """
    app_name = f"Regra_{str(id_regra).replace('-', '_')}"

    try:
        resp = requests.delete(f"{SIDDHI_RUNNER_URL}/{app_name}")
        resp.raise_for_status()
        print(f"[SIDDHI] Regra {id_regra} removida com sucesso do Siddhi Runner.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"[SIDDHI] Erro ao remover regra {id_regra} do Siddhi Runner: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"[SIDDHI] Resposta do erro: {e.response.text}")
        return False
