import requests
import time
import json
import math

SIDDHI_ENDPOINT = "http://localhost:8080/eventos"
ARQUIVO_JSON = "../data/tweets.json"

print(f"🚀 Iniciando canhão de dados contínuo para: {SIDDHI_ENDPOINT}\n")

# Usar uma Session melhora drasticamente a performance para envios massivos
sessao = requests.Session()
contador_sucesso = 0
contador_erro = 0

try:
    with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
        for linha in f:
            if not linha.strip():
                continue

            tweet = json.loads(linha)

            tweet_limpo = {
                k: (None if isinstance(v, float) and math.isnan(v) else v)
                for k, v in tweet.items()
            }

            payload_formatado = {"event": tweet_limpo}

            try:
                resposta = sessao.post(
                    SIDDHI_ENDPOINT, json=payload_formatado, timeout=5
                )

                if resposta.status_code in [200, 201, 202]:
                    contador_sucesso += 1
                else:
                    contador_erro += 1
                    print(f"[ERRO {resposta.status_code}] Falha: {resposta.text}")

            except requests.exceptions.RequestException as e:
                print(f"[ERRO DE REDE] O Siddhi pode ter saturado ou caído: {e}")
                time.sleep(2)
            total_processado = contador_sucesso + contador_erro
            if total_processado % 1000 == 0:
                print(
                    f"📊 Status: {contador_sucesso} enviados com sucesso | {contador_erro} erros..."
                )

            time.sleep(0.01)

except FileNotFoundError:
    print(f"❌ Arquivo '{ARQUIVO_JSON}' não encontrado!")
except KeyboardInterrupt:
    print("\n🛑 Envio interrompido pelo usuário (Ctrl+C).")

print(
    f"\n✅ Fluxo finalizado ou interrompido! Total: {contador_sucesso} sucessos | {contador_erro} erros."
)
