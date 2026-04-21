import uuid
from sqlalchemy import Column, String, Text, BigInteger, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from .database import Base


class RegraCEP(Base):
    __tablename__ = "regras_cep"
    id_regra = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payload_regra = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="Sugerida")

    num_ocorrencias = Column(BigInteger, default=0)
    ultima_ocorrencia = Column(DateTime(timezone=True), nullable=True)
    score_relevancia = Column(Numeric(10, 4), default=0.0000)

    dt_criacao = Column(DateTime(True), server_default=func.now())
    dt_atualizacao = Column(DateTime(True), server_default=func.now())

    def __repr__(self):
        return f"<Regra CEP(id={self.id_regra}, status={self.status}, payload={self.payload_regra}, score={self.score_relevancia})>"
