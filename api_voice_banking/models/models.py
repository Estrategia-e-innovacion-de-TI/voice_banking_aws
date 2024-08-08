from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from config.database import Base


class User(Base):
    __tablename__ = "client"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True)
    email = Column(String(50), unique=True, index=True)
    direccion = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, index=True)
    password = Column(String(100), nullable=False)
    transactions = relationship("Transaction", back_populates="owner")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_client = Column(Integer, ForeignKey('client.id'), nullable=False)
    monto = Column(Float, nullable=False)
    fecha = Column(DateTime, nullable=False)
    owner = relationship("User", back_populates="transactions")