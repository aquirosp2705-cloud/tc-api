from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI()

data = []

class Movimiento(BaseModel):
    tarjeta: str
    fecha: str
    concepto: str
    pago: float

@app.get("/")
def root():
    return {"ok": True}

@app.get("/movimientos")
def listar():
    return data

@app.post("/movimientos")
def guardar(mov: Movimiento):
    data.append(mov.dict())
    return {"ok": True, "data": mov}
