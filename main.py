from datetime import datetime
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path("consumos_tc.db")

CONCEPTOS = [
    "Supermercado",
    "Restaurant",
    "Transporte",
    "Medicinas",
    "Doctor",
    "Salud",
    "Compras exterior",
    "Tecnología",
    "Hogar",
    "Servicios",
    "Ropa",
    "Otros",
]

TIPOS_CONSUMO = ["Corriente", "Diferido"]
TARJETAS = ["Pichincha", "Produbanco"]


class MovimientoIn(BaseModel):
    tarjeta: Literal["Pichincha", "Produbanco"]
    fecha: str = Field(default_factory=lambda: datetime.today().strftime("%Y-%m-%d"))
    concepto_resumen: str
    concepto_detallado: str = ""
    tipo_consumo: Literal["Corriente", "Diferido"] = "Corriente"
    numero_cuotas_pagadas: float = 0
    numero_cuotas_por_pagar: float = 0
    valor_cuota: float = 0
    ajuste: float = 0
    pago: float = 0


class MovimientoOut(BaseModel):
    id: int
    tarjeta: str
    fecha: str
    concepto_resumen: str
    concepto_detallado: str
    tipo_consumo: str
    numero_cuotas_pagadas: float
    numero_cuotas_por_pagar: float
    valor_cuota: float
    ajuste: float
    pago: float
    saldo: float
    saldo_diferido: float
    created_at: str


app = FastAPI(title="API Consumos TC", version="2.0.0")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tarjeta TEXT NOT NULL,
                fecha TEXT NOT NULL,
                concepto_resumen TEXT NOT NULL,
                concepto_detallado TEXT DEFAULT '',
                tipo_consumo TEXT NOT NULL,
                numero_cuotas_pagadas REAL DEFAULT 0,
                numero_cuotas_por_pagar REAL DEFAULT 0,
                valor_cuota REAL DEFAULT 0,
                ajuste REAL DEFAULT 0,
                pago REAL DEFAULT 0,
                saldo REAL DEFAULT 0,
                saldo_diferido REAL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)


@app.on_event("startup")
def startup():
    init_db()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "tarjeta": row["tarjeta"],
        "fecha": row["fecha"],
        "concepto_resumen": row["concepto_resumen"],
        "concepto_detallado": row["concepto_detallado"],
        "tipo_consumo": row["tipo_consumo"],
        "numero_cuotas_pagadas": row["numero_cuotas_pagadas"],
        "numero_cuotas_por_pagar": row["numero_cuotas_por_pagar"],
        "valor_cuota": row["valor_cuota"],
        "ajuste": row["ajuste"],
        "pago": row["pago"],
        "saldo": row["saldo"],
        "saldo_diferido": row["saldo_diferido"],
        "created_at": row["created_at"],
    }


def saldo_anterior(conn: sqlite3.Connection, tarjeta: str) -> float:
    row = conn.execute(
        "SELECT saldo FROM movimientos WHERE tarjeta = ? ORDER BY id DESC LIMIT 1",
        (tarjeta,)
    ).fetchone()
    return float(row["saldo"]) if row else 0.0


def recalcular_tarjeta(conn: sqlite3.Connection, tarjeta: str):
    rows = conn.execute(
        "SELECT * FROM movimientos WHERE tarjeta = ? ORDER BY id ASC",
        (tarjeta,)
    ).fetchall()

    saldo_corriente = 0.0
    for row in rows:
        pago = float(row["pago"] or 0)
        ajuste = float(row["ajuste"] or 0)
        valor_cuota = float(row["valor_cuota"] or 0)
        cuotas_por_pagar = float(row["numero_cuotas_por_pagar"] or 0)
        tipo = row["tipo_consumo"]

        saldo_corriente += pago + ajuste
        saldo_diferido = valor_cuota * cuotas_por_pagar if tipo == "Diferido" else 0.0

        conn.execute(
            "UPDATE movimientos SET saldo = ?, saldo_diferido = ? WHERE id = ?",
            (saldo_corriente, saldo_diferido, row["id"])
        )


@app.get("/")
def root():
    return {
        "ok": True,
        "mensaje": "API Consumos TC con base de datos funcionando",
        "tarjetas": TARJETAS,
    }


@app.get("/tarjetas")
def tarjetas():
    return {"tarjetas": TARJETAS}


@app.get("/conceptos")
def conceptos():
    return {"conceptos": CONCEPTOS}


@app.get("/movimientos/{tarjeta}", response_model=List[MovimientoOut])
def listar_movimientos(tarjeta: Literal["Pichincha", "Produbanco"]):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM movimientos WHERE tarjeta = ? ORDER BY id DESC",
            (tarjeta,)
        ).fetchall()
        return [row_to_dict(r) for r in rows]


@app.get("/saldo/{tarjeta}")
def saldo_tarjeta(tarjeta: Literal["Pichincha", "Produbanco"]):
    with get_conn() as conn:
        saldo = saldo_anterior(conn, tarjeta)
        row = conn.execute(
            "SELECT saldo_diferido, id FROM movimientos WHERE tarjeta = ? ORDER BY id DESC LIMIT 1",
            (tarjeta,)
        ).fetchone()

        return {
            "tarjeta": tarjeta,
            "saldo": saldo,
            "saldo_diferido_ultima_linea": float(row["saldo_diferido"]) if row else 0.0,
            "ultimo_id": int(row["id"]) if row else None,
        }


@app.post("/movimientos")
def crear_movimiento(mov: MovimientoIn):
    if mov.concepto_resumen not in CONCEPTOS:
        raise HTTPException(status_code=400, detail="Concepto_Resumen no válido.")

    cuotas_pagadas = mov.numero_cuotas_pagadas
    cuotas_por_pagar = mov.numero_cuotas_por_pagar
    valor_cuota = mov.valor_cuota
    ajuste = mov.ajuste

    if mov.tipo_consumo == "Corriente":
        cuotas_pagadas = 0
        cuotas_por_pagar = 0
        valor_cuota = 0
        ajuste = 0

    with get_conn() as conn:
        saldo_prev = saldo_anterior(conn, mov.tarjeta)
        saldo = saldo_prev + mov.pago + ajuste
        saldo_diferido = valor_cuota * cuotas_por_pagar if mov.tipo_consumo == "Diferido" else 0.0

        cur = conn.execute(
            """
            INSERT INTO movimientos (
                tarjeta, fecha, concepto_resumen, concepto_detallado, tipo_consumo,
                numero_cuotas_pagadas, numero_cuotas_por_pagar, valor_cuota,
                ajuste, pago, saldo, saldo_diferido, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mov.tarjeta,
                mov.fecha,
                mov.concepto_resumen,
                mov.concepto_detallado,
                mov.tipo_consumo,
                cuotas_pagadas,
                cuotas_por_pagar,
                valor_cuota,
                ajuste,
                mov.pago,
                saldo,
                saldo_diferido,
                datetime.now().isoformat(timespec="seconds"),
            )
        )

        row = conn.execute(
            "SELECT * FROM movimientos WHERE id = ?",
            (cur.lastrowid,)
        ).fetchone()

        return {"ok": True, "movimiento": row_to_dict(row)}


@app.delete("/movimientos/{tarjeta}/{id_registro}")
def eliminar_movimiento(tarjeta: Literal["Pichincha", "Produbanco"], id_registro: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM movimientos WHERE id = ? AND tarjeta = ?",
            (id_registro, tarjeta)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="No se encontró el registro.")

        conn.execute(
            "DELETE FROM movimientos WHERE id = ? AND tarjeta = ?",
            (id_registro, tarjeta)
        )

        recalcular_tarjeta(conn, tarjeta)

        return {"ok": True, "eliminado": id_registro, "tarjeta": tarjeta}
