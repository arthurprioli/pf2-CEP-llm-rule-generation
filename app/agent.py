import os

from datetime import datetime, timedelta, timezone
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

BASE_APP_NAME = "MonitoramentoRealTime"


def get_app_name():
    return BASE_APP_NAME

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

        from collections import Counter

        usuarios = Counter(d[0] for d in dados)
        acoes = Counter(d[2] for d in dados)

        linhas_eventos = [
            f"  - usuario='{d[0]}' acao='{d[2]}' texto={d[1]!r}" for d in dados
        ]
        resumo = (
            f"TOTAL_EVENTOS: {len(dados)}\n"
            f"DISTRIBUICAO_POR_ACAO: {dict(acoes)}\n"
            f"TOP_USUARIOS: {dict(usuarios.most_common(5))}\n"
            f"EVENTOS:\n" + "\n".join(linhas_eventos)
        )
        return resumo
    except Exception as e:
        print(e)


def limpa_cache_siddhi():
    """
    Limpa o cache do siddhi a cada refeeding para evitar estourar a memória
    """
    try:
        requests.post(
            SIDDHI_QUERY_URL,
            json={"appName": get_app_name(), "query": "delete CacheEventos on true;"},
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
        tempo_limite = datetime.now(timezone.utc) - timedelta(days=7)
        aprovadas = (
            db.query(models.RegraCEP).filter(models.RegraCEP.status == "Aprovada").all()
        )
        recusadas = (
            db.query(models.RegraCEP).filter(models.RegraCEP.status == "Recusada").all()
        )
        scores_atualizados = False
        for regra in aprovadas:
            if not regra.ultima_ocorrencia or regra.ultima_ocorrencia < tempo_limite:
                regra.score_relevancia *= Decimal("0.95")
                scores_atualizados = True
                print(f"Score da regra {regra.id_regra} reduzido para {regra.score_relevancia}")
        if scores_atualizados:
            db.commit()

        amostra_dados = pegar_amostra_refeeding()
        if not amostra_dados:
            print("Nenhum dado passado no Siddhi")
            return

        sugestoes = gerar_sugestoes(amostra_dados, recusadas)

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
    prompt_template = PromptTemplate.from_template("""Você é um Cientista de Dados Sênior e Especialista em Complex Event Processing (CEP).
        Sua tarefa: analisar a amostra REAL abaixo e gerar UMA regra SiddhiQL que detecte um padrão REALMENTE observável nesses dados — ações coordenadas, repetição de usuário, concentração temática, picos por tipo de ação, etc.

        AMOSTRA REAL CAPTURADA (não use o exemplo no final como base — ele é só sintaxe):
        ---
        {dados_reais}
        ---

        REGRAS PREVIAMENTE RECUSADAS (NÃO gere nada parecido com isto):
        ---
        {contexto_negativo}
        ---

        ANTES DE ESCREVER A REGRA, analise mentalmente:
        - Qual 'acao' aparece com maior frequência? Vale a pena filtrar por ela?
        - Algum 'usuario' aparece repetido? Isso sugere agregação por usuario.
        - Há concentração temática no campo 'texto' (ex.: várias menções a um mesmo tópico)? Use str:contains() ou regex.
        - O threshold do having (ex.: quantidade > N) precisa fazer sentido dado o TOTAL_EVENTOS — não escolha um threshold que nunca dispararia.

        A regra DEVE refletir um padrão presente NOS DADOS ACIMA. Não copie o exemplo cegamente.

        INSTRUÇÕES RÍGIDAS DE SINTAXE (Siga a gramática estrita do motor WSO2 Siddhi):
        1. Cabeçalho da App: O script deve iniciar definindo o nome do app. Ex: @App:name('AnaliseRedeSocialIA')
        2. Stream de Entrada: Deve ser OBRIGATORIAMENTE declarada exatamente assim para ouvir o tráfego interno:
        @source(type='inMemory', topic='EventosSimulador')
        define stream FluxoEntrada (usuario string, texto string, acao string);
        3. Stream de Saída (Gatilho HTTP): A regra DEVE enviar um POST para a nossa API. Declare a saída OBRIGATORIAMENTE assim:
        @sink(type='http', publisher.url='http://host.docker.internal:8000/regras/matches', method='POST', @map(type='json'))
        define stream AlertasStream (id_regra string, usuario string, tipo_alerta string, quantidade long);
        4. Ordem Estrita da Query: Você deve seguir a ordem canônica do SiddhiQL:
        from [Janela/Filtro] -> select -> group by -> having -> insert into.
        *PROIBIDO* colocar 'group by' ou 'having' antes do 'select'.
        5. Tipagem e Aliases: O resultado de funções agregadas como count() deve receber o alias 'quantidade' (que é do tipo long) para bater com a AlertasStream. O atributo 'tipo_alerta' deve ser uma string descritiva.
        6. Identificação da Regra: O SELECT DEVE incluir OBRIGATORIAMENTE, como PRIMEIRA coluna, a literal string 'ID_REGRA_PLACEHOLDER' com alias 'id_regra'. Exemplo: select 'ID_REGRA_PLACEHOLDER' as id_regra, usuario, ...
        Esse placeholder será substituído pelo UUID real no momento do deploy. NÃO altere o texto 'ID_REGRA_PLACEHOLDER'.

        REQUISITO DE SAÍDA:
        Retorne EXCLUSIVAMENTE um array JSON válido contendo o código SiddhiQL em uma única linha dentro do campo "payload". Não adicione blocos de código Markdown (```json), explicações ou introduções.

        EXEMPLO DE RETORNO ESPERADO (APENAS PARA REFERÊNCIA DE SINTAXE — NÃO copie o filtro, o tipo_alerta nem o threshold):
        [
        {{"payload": "@App:name('DetectaSpamIA') @source(type='inMemory', topic='EventosSimulador') define stream FluxoEntrada (usuario string, texto string, acao string); @sink(type='http', publisher.url='http://host.docker.internal:8000/regras/matches', method='POST', @map(type='json')) define stream AlertasStream (id_regra string, usuario string, tipo_alerta string, quantidade long); from FluxoEntrada[acao == 'postar_link']#window.time(1 min) select 'ID_REGRA_PLACEHOLDER' as id_regra, usuario, 'Spam Coordenado' as tipo_alerta, count() as quantidade group by usuario having quantidade > 5 insert into AlertasStream;"}}
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