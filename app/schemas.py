from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class RegraBase(BaseModel):
    payload_regra: str


class RegraCreate(RegraBase):
    pass


class RegraStatusUpdate(BaseModel):
    status: str = Field(
        ..., pattern="^(Aprovada|Recusada|Manual|Sugerida para remoção)$"
    )


class RegraResponse(RegraBase):
    id_regra: UUID
    status: str
    num_ocorrencias: int
    ultima_ocorrencia: datetime | None
    score_relevancia: float
    dt_criacao: datetime
    dt_atualizacao: datetime

    model_config = ConfigDict(from_attributes=True)


class MatchPayload(BaseModel):
    id_regra: UUID
    alerta: str = "PADRÃO DETECTADO NOS SEUS DADOS"
