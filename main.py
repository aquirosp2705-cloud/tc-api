from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from datetime import datetime

app = FastAPI(title="API Consumos TC", version="2.0.0")

# 🔥 CORS (CLAVE PARA QUE FUNCIONE LA WEB)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = "consumos.db"

# ----------------------------
# MODELO
# ----------------------------
class Movimiento(BaseModel):
    tarjeta: str
    fecha: str
    concepto_resumen: str
    concepto_detallado: str
    tipo_consumo: str
    numero_cuotas_pagadas: int = 0
    numero_cuotas_por_pagar: int = 0
    valor_cuota: float = 0
    ajuste: float = 0
    pago: float = 0

# ----------------------------
# DB INIT
# ----------------------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS movimientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarjeta TEXT,
        fecha TEXT,
        concepto_resumen TEXT,
        concepto_detallado TEXT,
        tipo_consumo TEXT,
        cuotas_pagadas INTEGER,
        cuotas_por_pagar INTEGER,
        valor_cuota REAL,
        ajuste REAL,
        pago REAL,
        saldo REAL,
        saldo_diferido REAL
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ----------------------------
# HELPERS
# ----------------------------
def get_last_saldo(tarjeta):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT saldo FROM movimientos WHERE tarjeta=? ORDER BY id DESC LIMIT 1", (tarjeta,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_last_saldo_diferido(tarjeta):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT saldo_diferido FROM movimientos WHERE tarjeta=? ORDER BY id DESC LIMIT 1", (tarjeta,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ----------------------------
# ENDPOINTS
# ----------------------------
@app.get("/")
def root():
    return {"msg": "API funcionando"}

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.get("/conceptos")
def conceptos():
    return {
        "conceptos": [
            "Alimentación","Transporte","Suscripciones","Salud","Educación",
            "Tecnología","Hogar","Servicios","Ropa","Otros"
        ]
    }

# ----------------------------
# GUARDAR MOVIMIENTO
# ----------------------------
@app.post("/movimientos")
def crear_movimiento(mov: Movimiento):

    saldo_anterior = get_last_saldo(mov.tarjeta)

    # 🔥 SALDO SOLO USA PAGO + AJUSTE
    saldo = saldo_anterior + mov.pago + mov.ajuste

    # 🔥 DIFERIDO
    if mov.tipo_consumo == "Diferido":
        saldo_diferido = mov.valor_cuota * mov.numero_cuotas_por_pagar
    else:
        saldo_diferido = 0

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""
    INSERT INTO movimientos (
        tarjeta, fecha, concepto_resumen, concepto_detallado,
        tipo_consumo, cuotas_pagadas, cuotas_por_pagar,
        valor_cuota, ajuste, pago, saldo, saldo_diferido
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        mov.tarjeta,
        mov.fecha,
        mov.concepto_resumen,
        mov.concepto_detallado,
        mov.tipo_consumo,
        mov.numero_cuotas_pagadas,
        mov.numero_cuotas_por_pagar,
        mov.valor_cuota,
        mov.ajuste,
        mov.pago,
        saldo,
        saldo_diferido
    ))

    conn.commit()
    conn.close()

    return {"ok": True, "saldo": saldo}

# ----------------------------
# LISTAR
# ----------------------------
@app.get("/movimientos/{tarjeta}")
def listar_movimientos(tarjeta: str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""
    SELECT * FROM movimientos WHERE tarjeta=?
    ORDER BY id DESC
    """, (tarjeta,))

    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "tarjeta": r[1],
            "fecha": r[2],
            "concepto_resumen": r[3],
            "concepto_detallado": r[4],
            "tipo_consumo": r[5],
            "numero_cuotas_pagadas": r[6],
            "numero_cuotas_por_pagar": r[7],
            "valor_cuota": r[8],
            "ajuste": r[9],
            "pago": r[10],
            "saldo": r[11],
            "saldo_diferido": r[12]
        })

    return result

# ----------------------------
# SALDO
# ----------------------------
@app.get("/saldo/{tarjeta}")
def saldo(tarjeta: str):
    return {
        "saldo": get_last_saldo(tarjeta),
        "saldo_diferido_ultima_linea": get_last_saldo_diferido(tarjeta)
    }

# ----------------------------
# ELIMINAR
# ----------------------------
@app.delete("/movimientos/{tarjeta}/{id}")
def eliminar_movimiento(tarjeta: str, id: int):

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("DELETE FROM movimientos WHERE id=? AND tarjeta=?", (id, tarjeta))
    conn.commit()

    conn.close()

    return {"ok": True}
