from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from .database import engine, get_db
from .siddhi_client import siddhi
from .agent import executar_refeeding


def _get_db():
    from .database import get_db as _real_get_db

    yield from _real_get_db()


from . import models, schemas

app = FastAPI(
    title="API para inserção de regras CEP",
    description="API para orquestrar agente de IA, motor CEP e banco de regras",
    version="0.1.0",
)

models.Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="app/templates")


@app.get("/regras", response_model=List[schemas.RegraResponse])
def listar_regras(status_regra: str = None, db: Session = Depends(_get_db)):
    """
    Faz a listagem das regras do banco.
    """
    query = db.query(models.RegraCEP)
    if status_regra:
        query = query.filter(models.RegraCEP.status == status_regra)

    return query.order_by(models.RegraCEP.score_relevancia.desc()).all()


@app.post(
    "/regras/manual",
    response_model=schemas.RegraResponse,
    status_code=status.HTTP_201_CREATED,
)
def criar_regra_manual(regra: schemas.RegraCreate, db: Session = Depends(_get_db)):
    """
    Cria a regra manual no banco de regras
    @TODO Injetar no siddhi quando criar o agente CEP e integrar
    """
    nova_regra = models.RegraCEP(payload_regra=regra.payload_regra, status="Manual")
    db.add(nova_regra)
    db.commit()
    db.refresh(nova_regra)

    sucesso = siddhi.deploy_rule(nova_regra.id_regra, nova_regra.payload_regra)
    if not sucesso:
        print("WARNING: Regra salva no banco, mas falha ao iniciar no CEP.")

    print(f"[INJEÇÃO DE REGRA] Injetando regra MANUAL {nova_regra.id_regra} no Siddhi")
    return nova_regra


@app.post("/regras/matches", status_code=status.HTTP_200_OK)
def registrar_match(envelope: schemas.MatchPayloadEnvelope, db: Session = Depends(_get_db)):
    """
    Endpoint para receber notificações de matches do Siddhi.
    O Siddhi JSON sink envia o evento em `{"event": {...}}`.
    """
    match = envelope.event
    regra = (
        db.query(models.RegraCEP)
        .filter(models.RegraCEP.id_regra == match.id_regra)
        .first()
    )

    if not regra:
        raise HTTPException(
            status_code=404, detail=f"Regra {match.id_regra} não encontrada"
        )

    regra.num_ocorrencias += 1
    regra.ultima_ocorrencia = datetime.now(timezone.utc)

    db.commit()

    print(
        f"[MATCH DETECTADO] Regra {match.id_regra} disparou para {match.usuario} "
        f"({match.tipo_alerta}, quantidade={match.quantidade}). "
        f"Total de ocorrências: {regra.num_ocorrencias}"
    )
    return {"status": "Sucesso!", "mensagem": "Score atualizado!"}


@app.put("/regras/{id_regra}/status", response_model=schemas.RegraResponse)
def atualizar_status_regra(
    id_regra: UUID,
    update_data: schemas.RegraStatusUpdate,
    db: Session = Depends(_get_db),
):
    """
    Atualiza o status de uma regra (Sugerida -> Aprovada/Recusada)
    """

    regra = (
        db.query(models.RegraCEP).filter(models.RegraCEP.id_regra == id_regra).first()
    )
    if not regra:
        raise HTTPException(status_code=404, detail=f"Regra {id_regra} não encontrada")

    regra.status = update_data.status
    db.commit()
    db.refresh(regra)

    if regra.status == "Aprovada":
        print(
            f"[ATUALIZAÇÃO DE REGRA] Regra APROVADA! Atualizando {regra.id_regra} no Siddhi"
        )
        siddhi.deploy_rule(str(regra.id_regra), regra.payload_regra)
    elif regra.status == "Recusada":
        print(
            f"[ATUALIZAÇÃO DE REGRA] Regra RECUSADA! Atualizando {regra.id_regra} no Siddhi"
        )
        siddhi.remove_rule(str(regra.id_regra))

    return regra


@app.get("/painel", response_class=HTMLResponse)
def painel(request: Request, db: Session = Depends(_get_db)):
    """Interface visual da tabela de regras"""
    regras = (
        db.query(models.RegraCEP)
        .order_by(
            models.RegraCEP.status,
            models.RegraCEP.num_ocorrencias.desc(),
        )
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="painel.html",
        context={"request": request, "regras": regras},
    )


@app.post("/agente/refeed")
def rodar_agente():
    executar_refeeding()
    return {"status": "Refeeding executado"}
