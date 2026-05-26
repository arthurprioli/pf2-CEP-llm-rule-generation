import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal
from .siddhi_client import siddhi

PROMPT_PATH = Path(__file__).parent / "prompts" / "refeeder.txt"
JANELA_DECAIMENTO = timedelta(days=7)
FATOR_DECAIMENTO = Decimal("0.95")
SCORE_INICIAL_SUGESTAO = 0.5

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
)


def _decair_scores(db: Session, aprovadas: list[models.RegraCEP]) -> bool:
    """Reduz o score das regras aprovadas que não disparam há mais de JANELA_DECAIMENTO."""
    limite = datetime.now(timezone.utc) - JANELA_DECAIMENTO
    alterado = False
    for regra in aprovadas:
        if not regra.ultima_ocorrencia or regra.ultima_ocorrencia < limite:
            regra.score_relevancia *= FATOR_DECAIMENTO
            alterado = True
            print(
                f"Score da regra {regra.id_regra} reduzido para {regra.score_relevancia}"
            )
    if alterado:
        db.commit()
    return alterado


def _formatar_amostra(registros: list[list]) -> str:
    """Formata os registros do CacheEventos num resumo legível para o LLM."""
    usuarios = Counter(r[0] for r in registros)
    dispositivos = Counter(r[2] for r in registros)
    eventos = [
        f"  - usuario='{r[0]}' dispositivo='{r[2]}' texto={r[1]!r}" for r in registros
    ]
    return (
        f"TOTAL_EVENTOS: {len(registros)}\n"
        f"DISTRIBUICAO_POR_DISPOSITIVO: {dict(dispositivos)}\n"
        f"TOP_USUARIOS: {dict(usuarios.most_common(5))}\n"
        f"EVENTOS:\n" + "\n".join(eventos)
    )


def _buscar_amostra() -> str | None:
    print("Consultando siddhi para coletar amostra de dados")
    registros = siddhi.fetch_cache()
    if not registros:
        return None
    return _formatar_amostra(registros)


def _sugerir_regras(amostra: str, recusadas: list[models.RegraCEP]) -> list[dict]:
    """Chama o LLM com a amostra e devolve a lista de sugestões parseadas."""
    template = PromptTemplate.from_template(PROMPT_PATH.read_text(encoding="utf-8"))
    contexto_negativo = (
        "\n".join(r.payload_regra for r in recusadas) if recusadas else "Nenhuma."
    )
    resposta = (template | llm).invoke(
        {"dados_reais": amostra, "contexto_negativo": contexto_negativo}
    )
    return _parse_resposta_llm(resposta.content)


def _parse_resposta_llm(texto: str) -> list[dict]:
    texto = texto.strip()
    if texto.startswith("```json"):
        texto = texto[len("```json"):]
    elif texto.startswith("```"):
        texto = texto[len("```"):]
    if texto.endswith("```"):
        texto = texto[:-3]
    try:
        return json.loads(texto.strip())
    except json.JSONDecodeError:
        print(f"❌ Erro ao decodificar resposta da IA. Texto bruto:\n{texto}")
        return []


def _persistir_sugestoes(db: Session, sugestoes: list[dict]) -> None:
    for sug in sugestoes:
        nova = models.RegraCEP(
            payload_regra=sug["payload"],
            status="Sugerida",
            score_relevancia=SCORE_INICIAL_SUGESTAO,
        )
        db.add(nova)
        print(f"Nova sugestão de regra: {sug['payload']}")
    db.commit()


def executar_refeeding() -> None:
    """Orquestra um ciclo de refeeding: decay → amostra → sugestões → cleanup."""
    db = SessionLocal()
    try:
        print(f"Analisando banco de regras às {datetime.now()}")
        aprovadas = (
            db.query(models.RegraCEP).filter(models.RegraCEP.status == "Aprovada").all()
        )
        recusadas = (
            db.query(models.RegraCEP).filter(models.RegraCEP.status == "Recusada").all()
        )

        _decair_scores(db, aprovadas)

        amostra = _buscar_amostra()
        if not amostra:
            print("Nenhum dado passado no Siddhi")
            return

        sugestoes = _sugerir_regras(amostra, recusadas)
        if sugestoes:
            _persistir_sugestoes(db, sugestoes)

        siddhi.clear_cache()
    except Exception as e:
        print(f"[REFEED] Falha no ciclo de refeeding: {e}")
    finally:
        db.close()
