import os

from datetime import datetime, timedelta
from decimal import Decimal
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from .database import SessionLocal
from . import models, schemas
import requests
import json

api_key = os.getenv("GEMINI_API_KEY")
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key)

SIDDHI_QUERY_URL = os.getenv("SIDDHI_QUERY_URL")
SIDDHI_RUNNER_URL = os.getenv("SIDDHI_RUNNER_URL")

def get_app_name():
    apps = requests.get(SIDDHI_RUNNER_URL, auth=('admin', 'admin')).json()
    if not apps:
        print("Motor sem regras ativas...")
        return None
    
    nome_app = apps[0]
    return nome_app

def pegar_amostra_refeeding():
    query = {
        "appName": get_app_name(),
        "query": "from CacheEventos select *;",
    }

    try:
        print("Consultando siddhi para coletar amostra de dados")
        response = requests.post(SIDDHI_QUERY_URL, json=query, auth=('admin', 'admin'), timeout=5)
        
        if response.status_code != 200:
            print(f"ERRO DO SIDDHI ({response.status_code}): {response.text}")
            return None

        dados = response.json().get("records", [])
        if not dados:
            return None

        dados_formatados = []
        for dado in dados:
            dados_formatados.append(f"Usuário: {dado[0]} | Texto: {dado[1]} | Ação: {dado[2]}")

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
            json={"appName": get_app_name(), "query": "delete CacheEventos;"},
            auth=("admin", "admin"),
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
        tempo_limite = datetime.now() - timedelta(days=7)
        aprovadas = (
            db.query(models.RegraCEP).filter(models.RegraCEP.status == "Aprovada").all()
        )
        recusadas = (
            db.query(models.RegraCEP).filter(models.RegraCEP.status == "Recusada").all()
        )
        for regra in aprovadas:
            if not regra.ultima_ocorrencia or regra.ultima_ocorrencia < tempo_limite:
                regra.score_relevancia *= Decimal(0.95)  # colocar dinâmismo?
                print(f"Score da regra {regra.id_regra} reduzido")

        amostra_dados = pegar_amostra_refeeding()
        if not amostra_dados:
            print("Nenhum dado passado no Siddhi")
            return

        sugestoes = gerar_sugestoes(aprovadas, recusadas)

        for sug in sugestoes:
            nova_regra = models.RegraCEP(
                payload_regra=sug["payload"], status="Sugerida", score_relevancia=0.5
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
    prompt_template = PromptTemplate.from_template("""Você é um Cientista de Dados e Especialista em Complex Event Processing (CEP).
    Sua tarefa é analisar DADOS REAIS e criar 1 nova regra SiddhiQL para detectar ataques (ex: brute_force, ataque_db, compra_suspeita).

    DADOS REAIS CAPTURADOS:
    ---
    {dados_reais}
    ---

    INSTRUÇÕES RÍGIDAS (Siga a gramática estrita do motor WSO2 Siddhi):
    1. A stream de entrada DEVE OBRIGATORIAMENTE ser: 
       @source(type='inMemory', topic='EventosSimulador') 
       define stream FluxoEntrada (usuario string, texto string, acao string);
    2. A regra DEVE ter um nome único, ex: @App:name('DetectaAnomaliaIA')
    3. Crie uma stream de saída com log, usando tipos de dados corretos (count() retorna 'long'): 
       @sink(type='log', prefix='[ALERTA IA]') 
       define stream AlertasStream (usuario string, tipo_alerta string, quantidade long);
    4. ORDEM OBRIGATÓRIA DA QUERY: Você deve seguir ESTRITAMENTE esta ordem: 'from' -> 'select' -> 'group by' -> 'having' -> 'insert into'. NUNCA coloque 'group by' antes do 'select'.
    5. RETORNE EXCLUSIVAMENTE UM ARRAY JSON VÁLIDO. Sem explicações, sem blocos markdown.
    
    EXEMPLO DE RESPOSTA ESPERADA:
    [
      {{"payload": "@App:name('BloqueioAtaqueIA') @source(type='inMemory', topic='EventosSimulador') define stream FluxoEntrada (usuario string, texto string, acao string); @sink(type='log', prefix='[ALERTA]') define stream AlertasStream (usuario string, tentativas long); from FluxoEntrada[acao == 'ataque_db']#window.timeBatch(10 sec) select usuario, count() as tentativas group by usuario having tentativas > 3 insert into AlertasStream;"}}
    ]
    """)

    recusadas_str = "\n".join([r.payload_regra for r in recusadas]) if recusadas else "Nenhuma."

    chain = prompt_template | llm
    resposta = chain.invoke(
        {"dados_reais": dados_reais, "contexto_negativo": recusadas_str}
    )

    texto_ia = resposta.content.strip()
    
    # Limpa a formatação markdown se a IA teimar em enviá-la
    if texto_ia.startswith("```json"):
        texto_ia = texto_ia.replace("```json", "")
    if texto_ia.startswith("```"):
        texto_ia = texto_ia.replace("```", "")
    if texto_ia.endswith("```"):
        texto_ia = texto_ia[:-3]

    try:
        sugestoes = json.loads(texto_ia.strip())
        return sugestoes
    except json.JSONDecodeError:
        print(f"❌ Erro ao decodificar a resposta da IA. Texto bruto recebido:\n{texto_ia}")
        return []