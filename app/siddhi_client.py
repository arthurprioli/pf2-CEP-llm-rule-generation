import os
import re

import requests

BASE_APP_NAME = "MonitoramentoRealTime"

_APP_NAME_RE = re.compile(r"@App:name\s*\(\s*['\"][^'\"]*['\"]\s*\)\s*")


def _rule_app_name(id_regra: str) -> str:
    return f"Regra_{str(id_regra).replace('-', '_')}"


class SiddhiClient:
    """Thin wrapper around the Siddhi Runner REST API."""

    def __init__(
        self,
        runner_url: str | None = None,
        query_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: float = 5.0,
        base_app: str = BASE_APP_NAME,
    ):
        self.runner_url = runner_url or os.getenv("SIDDHI_RUNNER_URL")
        self.query_url = query_url or os.getenv("SIDDHI_QUERY_URL")
        self.auth = (
            user or os.getenv("SIDDHI_USER", "admin"),
            password or os.getenv("SIDDHI_PASSWORD", "admin"),
        )
        self.timeout = timeout
        self.base_app = base_app

    def deploy_rule(self, id_regra: str, payload: str) -> bool:
        app_name = _rule_app_name(id_regra)
        payload = payload.replace("ID_REGRA_PLACEHOLDER", str(id_regra))
        if "ID_REGRA_PLACEHOLDER" in payload or str(id_regra) not in payload:
            print(
                f"[SIDDHI] AVISO: regra {id_regra} não contém id_regra no payload — "
                "matches não poderão ser correlacionados."
            )

        payload_sem_nome = _APP_NAME_RE.sub("", payload, count=1).lstrip()
        siddhi_app = f"@App:name('{app_name}')\n{payload_sem_nome}"

        try:
            resp = requests.post(
                self.runner_url,
                data=siddhi_app,
                headers={"Content-Type": "text/plain"},
                auth=self.auth,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            print(f"[SIDDHI] Regra {id_regra} implantada com sucesso.")
            return True
        except requests.RequestException as e:
            self._log_error(f"implantar regra {id_regra}", e)
            return False

    def remove_rule(self, id_regra: str) -> bool:
        app_name = _rule_app_name(id_regra)
        try:
            resp = requests.delete(
                f"{self.runner_url}/{app_name}",
                auth=self.auth,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            print(f"[SIDDHI] Regra {id_regra} removida com sucesso.")
            return True
        except requests.RequestException as e:
            self._log_error(f"remover regra {id_regra}", e)
            return False

    def store_query(self, query: str, app_name: str | None = None) -> list | None:
        """Execute a store query. Returns the `records` array, or None on failure."""
        try:
            resp = requests.post(
                self.query_url,
                json={"appName": app_name or self.base_app, "query": query},
                auth=self.auth,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            self._log_error("store query", e)
            return None

        if resp.status_code != 200:
            print(f"[SIDDHI] Erro store query ({resp.status_code}): {resp.text}")
            return None
        return resp.json().get("records", [])

    def fetch_cache(self) -> list | None:
        return self.store_query("from CacheEventos select *;")

    def clear_cache(self) -> bool:
        if self.store_query("delete CacheEventos on true;") is None:
            return False
        print("[SIDDHI] Cache limpo.")
        return True

    @staticmethod
    def _log_error(acao: str, e: requests.RequestException) -> None:
        print(f"[SIDDHI] Erro ao {acao}: {e}")
        if getattr(e, "response", None) is not None:
            print(f"[SIDDHI] Resposta do erro: {e.response.text}")


siddhi = SiddhiClient()
