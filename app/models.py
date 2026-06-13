from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy import Boolean, Float

from app.database import Base


class Empresa(Base):
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String)
    giro = Column(String)
    prompt_base = Column(String)
    status = Column(String, default="ACTIVA")

    numeros_whatsapp = relationship("NumeroWhatsApp", back_populates="empresa")
    clientes = relationship("Cliente", back_populates="empresa")
    conversaciones = relationship("Conversacion", back_populates="empresa")
    citas = relationship("Cita", back_populates="empresa")


class NumeroWhatsApp(Base):
    __tablename__ = "numeros_whatsapp"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"))

    telefono = Column(String, unique=True)
    phone_number_id = Column(String)
    token = Column(String)
    status = Column(String, default="ACTIVO")

    empresa = relationship("Empresa", back_populates="numeros_whatsapp")


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"))

    telefono = Column(String)
    nombre = Column(String)

    empresa = relationship("Empresa", back_populates="clientes")


class Conversacion(Base):
    __tablename__ = "conversaciones"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"))

    telefono = Column(String)
    mensaje = Column(String)
    respuesta = Column(String)

    paso = Column(String, nullable=True)
    servicio_id = Column(Integer, nullable=True)
    nombre = Column(String, nullable=True)
    fecha = Column(String, nullable=True)
    hora = Column(String, nullable=True)

    empresa = relationship(
        "Empresa",
        back_populates="conversaciones"
    )


class Cita(Base):
    __tablename__ = "citas"

    id = Column(Integer, primary_key=True, index=True)

    empresa_id = Column(Integer, ForeignKey("empresas.id"))
    servicio_id = Column(Integer, ForeignKey("servicios.id"), nullable=True)

    nombre = Column(String)
    telefono = Column(String)
    fecha = Column(String)
    hora = Column(String)

    status = Column(String, default="AGENDADA")
    recordatorio_enviado = Column(Boolean, default=False)

    empresa = relationship("Empresa", back_populates="citas")

    

class Servicio(Base):
    __tablename__ = "servicios"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"))

    nombre = Column(String)
    descripcion = Column(String)
    duracion = Column(Integer)
    precio = Column(Float)

    activo = Column(Boolean, default=True)