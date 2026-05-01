import os

from datetime import datetime, timedelta
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from .database import SessionLocal
from . import models, schemas
import requests

api_key = os.getenv("GEMINI_API_KEY")
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=api_key)

SIDDHI_QUERY_URL = "http://localhost:8006/query"


def pegar_amostra_refeeding():
    query = {
        "appName": "MonitoramentoRealTime",
        "query": "from CacheEventos select * limit 50",
    }

    try:
        print("Consultando siddhi para coletar amostra de dados")
        response = requests.post(SIDDHI_QUERY_URL, json=query, timeout=5)
        response.raise_for_status()

        dados = response.json().get("records", [])
        if not dados:
            return None

        dados_formatados = []
        for dado in dados:
            dados.append(f"Usuário: {dado[0]} | Texto: {dado[1]} | Ação: {dado[2]}")

        return "\n".join(dados_formatados)
    except Exception as e:
        print(e)


def limpa_cache_siddhi():
    """
    Limpa o cache do siddhi a cada refeeding para evitar estourar a memória
    """
    try:
        requests.post(
            SIDDHI_QUERY_URL,
            json={"appName": "MonitoramentoRealTime", "query": "delete CacheEventos"},
            timeout=5,
        )
        print("Cache do siddhi limpo!")
    except Exception as e:
        print(e)


def executar_refeeding():
    """Função que programa e roda o refeeding do agente"""
    db = SessionLocal()
    try:
        print(f"Analisando banco de regras às {datetime.now()}")
        tempo_limite = datetime.now() - datetime.timedelta(days=7)
        aprovadas = (
            db.query(models.RegraCEP).filter(models.RegraCEP.status == "Aprovada").all()
        )
        recusadas = (
            db.query(models.RegraCEP).filter(models.RegraCEP.status == "Recusada").all()
        )
        for regra in aprovadas:
            if not regra.ultima_ocorrencia or regra.ultima_ocorrencia < tempo_limite:
                regra.score *= 0.95  # colocar dinâmismo?
                print(f"Score da regra {regra.id_regra} reduzido")

        amostra_dados = pegar_amostra_refeeding()
        if not amostra_dados:
            print("Nenhum dado passado no Siddhi")
            return

        sugestoes = gerar_sugestoes(aprovadas, recusadas)

        for sug in sugestoes:
            nova_regra = models.RegraCEP(
                payload=sug["payload"], status="Sugerida", score_relevancia=0.5
            )
            db.add(nova_regra)
            print(f"Nova sugestão de regra: {sug['payload']}")
            db.commit()

        limpa_cache_siddhi()
    except Exception as e:
        print(e)
    finally:
        db.close()


def gerar_sugestoes(dados_reais, recusadas):
    """
    Pede pra LLM sugerir uma regra com base nas regras aprovadas e recusadas.
    """
    prompt_template = PromptTemplate.from_template("""Você é um Cientista de Dados e Especialista em Complex Event Processing (CEP).
    Sua tarefa é analisar uma amostra de DADOS REAIS recém-coletados e criar
    novas regras em linguagem SiddhiQL para detectar padrões, anomalias ou comportamentos 
    que você identificou NESSES dados específicos.

    DADOS REAIS CAPTURADOS NESTE CICLO (Minere estes dados):
    ---
    {dados_reais}
    ---

    REGRAS REJEITADAS ANTERIORMENTE (Blacklist - Não gere nada parecido com isto):
    ---
    {contexto_negativo}
    ---

    INSTRUÇÕES:
    1. Identifique padrões no texto dos 'DADOS REAIS' (ex: palavras que se repetem, ações suspeitas).
    2. Escreva 2 regras SiddhiQL que usem a stream 'FluxoEntrada (usuario string, texto string, acao string)' para disparar alertas quando esses padrões ocorrerem.
    3. Retorne APENAS o código SiddhiQL puro. Uma regra completa por linha. Sem blocos markdown, sem comentários.
    """)

    recusadas = "\n".join([r.payload_regra for r in recusadas]) if recusadas else None

    chain = prompt_template | llm
    resposta = chain.invoke(
        {"dados_reais": dados_reais, "contexto_negativo": recusadas}
    )

    linhas = resposta.content.strip().split("\n")
    return [{"payload": l.strip() for l in linhas if "define" in l.lower()}]
