"""Historial de precios en una base local (SQLite) y lista de seguimiento.

Cada búsqueda deja una observación por producto. Con eso se puede decir si un precio
es el más bajo que se ha visto y si el "antes" que anuncia la tienda se sostiene.

El historial solo crece con las búsquedas que una persona pide: aquí no hay nada que
consulte las tiendas por su cuenta ni de forma programada.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

from ofertas.entorno import RAIZ
from ofertas.modelos import Oferta, Resultado

# Base que vive solo mientras dura la búsqueda (para `--sin-historial`).
EN_MEMORIA = ":memory:"
# Si el mismo precio se vuelve a ver antes de este tiempo, no se guarda otra vez.
VENTANA_REPETIDOS = timedelta(hours=6)
# Para dudar de un descuento hace falta haber visto el producto varias veces y días.
MIN_OBSERVACIONES = 3
MIN_DIAS = 7
# Tolerancia para considerar que el precio de lista sí se llegó a ver.
TOLERANCIA_LISTA = 0.97

ESQUEMA = """
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY,
    tienda_id TEXT NOT NULL,
    clave TEXT NOT NULL,
    tienda TEXT NOT NULL,
    nombre TEXT NOT NULL,
    marca TEXT NOT NULL DEFAULT '',
    ean TEXT,
    url TEXT NOT NULL,
    UNIQUE (tienda_id, clave)
);
CREATE TABLE IF NOT EXISTS observaciones (
    id INTEGER PRIMARY KEY,
    producto_id INTEGER NOT NULL REFERENCES productos (id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    precio REAL NOT NULL CHECK (precio > 0),
    precio_lista REAL NOT NULL,
    consulta TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS observaciones_por_producto ON observaciones (producto_id, fecha);
CREATE INDEX IF NOT EXISTS productos_por_ean ON productos (ean);
CREATE TABLE IF NOT EXISTS seguimientos (
    id INTEGER PRIMARY KEY,
    consulta TEXT NOT NULL,
    tiendas TEXT NOT NULL DEFAULT '',
    precio_objetivo REAL,
    creado TEXT NOT NULL,
    ultimo_precio REAL,
    ultima_tienda TEXT,
    ultima_url TEXT,
    ultima_revision TEXT
);
CREATE TABLE IF NOT EXISTS cache_internacional (
    fuente TEXT NOT NULL,
    consulta TEXT NOT NULL,
    fecha TEXT NOT NULL,
    datos TEXT NOT NULL,
    PRIMARY KEY (fuente, consulta)
);
CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""


@dataclass
class Contexto:
    """Lo que el historial sabe de un producto antes de la observación actual."""

    veces: int
    primera_vez: str
    minimo: float
    maximo: float
    ultimo_precio: float
    ultima_fecha: str
    dias_observado: int
    mediana: float = 0.0

    def a_dict(self, oferta: Oferta) -> dict:
        return {
            "veces_visto": self.veces,
            "primera_vez": fecha_local(self.primera_vez),
            "dias_observado": self.dias_observado,
            "minimo_visto": self.minimo,
            "maximo_visto": self.maximo,
            "mediana_vista": self.mediana,
            "precio_anterior": self.ultimo_precio,
            "fecha_anterior": fecha_local(self.ultima_fecha),
            "lectura": leer(oferta, self),
        }


@dataclass
class Seguimiento:
    id: int
    consulta: str
    tiendas: list[str]
    precio_objetivo: float | None
    creado: str
    ultimo_precio: float | None
    ultima_tienda: str | None
    ultima_url: str | None
    ultima_revision: str | None


def ruta_base() -> Path:
    carpeta = Path(os.environ.get("OFERTAS_DATOS") or RAIZ / "datos")
    return carpeta / "historial.db"


def conectar(ruta: Path | str | None = None) -> sqlite3.Connection:
    if ruta == EN_MEMORIA:
        conexion = sqlite3.connect(EN_MEMORIA)
    else:
        ruta = Path(ruta) if ruta else ruta_base()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.executescript(ESQUEMA)
    return conexion


def clave_de(oferta: Oferta) -> str:
    """Identifica un producto dentro de su tienda: la URL sin parámetros de rastreo."""
    partes = urlsplit(oferta.url)
    return f"{partes.netloc}{partes.path}".rstrip("/").lower()


def _ahora(ahora: datetime | None) -> datetime:
    return ahora or datetime.now(UTC)


def fecha_local(iso: str, con_hora: bool = False) -> str:
    """Las fechas se guardan en UTC; para mostrarlas se pasan a la hora del equipo."""
    local = datetime.fromisoformat(iso).astimezone()
    return local.strftime("%Y-%m-%d %H:%M" if con_hora else "%Y-%m-%d")


def _pesos(valor: float) -> str:
    return "$" + f"{round(valor):,}".replace(",", ".")


def leer(oferta: Oferta, contexto: Contexto) -> str:
    """Resume en una frase qué dice el historial sobre el precio actual."""
    partes = []
    if oferta.precio < contexto.minimo:
        partes.append(f"el precio más bajo registrado (antes, mínimo {_pesos(contexto.minimo)})")
    elif oferta.precio == contexto.minimo:
        partes.append("igual al precio más bajo registrado")
    else:
        partes.append(f"se ha visto más barato: {_pesos(contexto.minimo)}")
    if oferta.precio != contexto.ultimo_precio:
        cambio = (oferta.precio - contexto.ultimo_precio) / contexto.ultimo_precio * 100
        verbo = "bajó" if cambio < 0 else "subió"
        partes.append(
            f"{verbo} {abs(cambio):.0f}% frente a {_pesos(contexto.ultimo_precio)}"
            f" del {fecha_local(contexto.ultima_fecha)}"
        )
    suficiente = contexto.veces >= MIN_OBSERVACIONES and contexto.dias_observado >= MIN_DIAS
    if oferta.descuento_pct and suficiente:
        if max(contexto.maximo, oferta.precio) < oferta.precio_lista * TOLERANCIA_LISTA:
            partes.append(
                f"descuento dudoso: nunca se vio a {_pesos(oferta.precio_lista)},"
                f" el máximo registrado es {_pesos(contexto.maximo)}"
            )
        else:
            partes.append("el precio de lista sí se llegó a ver")
    return "; ".join(partes)


def contexto_de(conexion: sqlite3.Connection, oferta: Oferta) -> Contexto | None:
    """Devuelve lo observado antes para este producto, o None si es la primera vez."""
    fila = conexion.execute(
        """
        SELECT COUNT(*) AS veces, MIN(o.fecha) AS primera, MAX(o.fecha) AS ultima,
               MIN(o.precio) AS minimo, MAX(o.precio) AS maximo
        FROM observaciones o JOIN productos p ON p.id = o.producto_id
        WHERE p.tienda_id = ? AND p.clave = ?
        """,
        (oferta.tienda_id, clave_de(oferta)),
    ).fetchone()
    if not fila["veces"]:
        return None
    precios = [
        f["precio"]
        for f in conexion.execute(
            """
            SELECT o.precio FROM observaciones o JOIN productos p ON p.id = o.producto_id
            WHERE p.tienda_id = ? AND p.clave = ? ORDER BY o.fecha, o.id
            """,
            (oferta.tienda_id, clave_de(oferta)),
        )
    ]
    dias = (datetime.fromisoformat(fila["ultima"]) - datetime.fromisoformat(fila["primera"])).days
    return Contexto(
        veces=fila["veces"],
        primera_vez=fila["primera"],
        minimo=fila["minimo"],
        maximo=fila["maximo"],
        ultimo_precio=precios[-1],
        ultima_fecha=fila["ultima"],
        dias_observado=dias,
        mediana=median(precios),
    )


def anotar(conexion: sqlite3.Connection, resultado: Resultado) -> None:
    """Agrega a cada oferta lo que el historial sabía de ella antes de esta búsqueda."""
    for oferta in resultado.ofertas:
        contexto = contexto_de(conexion, oferta)
        oferta.historial = contexto.a_dict(oferta) if contexto else None


def registrar(
    conexion: sqlite3.Connection, resultado: Resultado, ahora: datetime | None = None
) -> int:
    """Guarda una observación por oferta. Devuelve cuántas se guardaron."""
    momento = _ahora(ahora)
    guardadas = 0
    with conexion:
        for oferta in resultado.ofertas:
            clave = clave_de(oferta)
            if not clave or oferta.precio <= 0:
                continue
            conexion.execute(
                """
                INSERT INTO productos (tienda_id, clave, tienda, nombre, marca, ean, url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (tienda_id, clave) DO UPDATE SET
                    nombre = excluded.nombre, marca = excluded.marca, url = excluded.url,
                    ean = COALESCE(excluded.ean, productos.ean)
                """,
                (oferta.tienda_id, clave, oferta.tienda, oferta.nombre, oferta.marca,
                 oferta.ean, oferta.url),
            )
            producto_id = conexion.execute(
                "SELECT id FROM productos WHERE tienda_id = ? AND clave = ?",
                (oferta.tienda_id, clave),
            ).fetchone()["id"]
            ultima = conexion.execute(
                "SELECT fecha, precio, precio_lista FROM observaciones"
                " WHERE producto_id = ? ORDER BY fecha DESC, id DESC LIMIT 1",
                (producto_id,),
            ).fetchone()
            if (
                ultima
                and ultima["precio"] == oferta.precio
                and ultima["precio_lista"] == oferta.precio_lista
                and momento - datetime.fromisoformat(ultima["fecha"]) < VENTANA_REPETIDOS
            ):
                continue
            conexion.execute(
                "INSERT INTO observaciones (producto_id, fecha, precio, precio_lista, consulta)"
                " VALUES (?, ?, ?, ?, ?)",
                (producto_id, momento.isoformat(), oferta.precio, oferta.precio_lista,
                 resultado.consulta),
            )
            guardadas += 1
    return guardadas


def buscar_productos(conexion: sqlite3.Connection, texto: str, limite: int = 20) -> list[dict]:
    """Productos del historial cuyo nombre contiene todas las palabras de `texto`."""
    palabras = [p for p in texto.lower().split() if p]
    condicion = " AND ".join("LOWER(p.nombre || ' ' || p.marca) LIKE ?" for _ in palabras) or "1"
    filas = conexion.execute(
        f"""
        SELECT p.id, p.tienda, p.nombre, p.url, COUNT(o.id) AS veces,
               MIN(o.precio) AS minimo, MAX(o.precio) AS maximo,
               MIN(o.fecha) AS primera, MAX(o.fecha) AS ultima
        FROM productos p JOIN observaciones o ON o.producto_id = p.id
        WHERE {condicion}
        GROUP BY p.id ORDER BY ultima DESC, minimo ASC LIMIT ?
        """,
        (*(f"%{p}%" for p in palabras), limite),
    ).fetchall()
    salida = []
    for fila in filas:
        observaciones = conexion.execute(
            "SELECT fecha, precio, precio_lista FROM observaciones"
            " WHERE producto_id = ? ORDER BY fecha, id",
            (fila["id"],),
        ).fetchall()
        salida.append({**dict(fila), "observaciones": [dict(o) for o in observaciones]})
    return salida


# --- lista de seguimiento ---------------------------------------------------


def _a_seguimiento(fila: sqlite3.Row) -> Seguimiento:
    return Seguimiento(
        id=fila["id"],
        consulta=fila["consulta"],
        tiendas=[t for t in fila["tiendas"].split(",") if t],
        precio_objetivo=fila["precio_objetivo"],
        creado=fila["creado"],
        ultimo_precio=fila["ultimo_precio"],
        ultima_tienda=fila["ultima_tienda"],
        ultima_url=fila["ultima_url"],
        ultima_revision=fila["ultima_revision"],
    )


def seguir(
    conexion: sqlite3.Connection,
    consulta: str,
    tiendas: list[str] | None = None,
    precio_objetivo: float | None = None,
    ahora: datetime | None = None,
) -> Seguimiento:
    with conexion:
        cursor = conexion.execute(
            "INSERT INTO seguimientos (consulta, tiendas, precio_objetivo, creado)"
            " VALUES (?, ?, ?, ?)",
            (consulta.strip(), ",".join(tiendas or []), precio_objetivo,
             _ahora(ahora).isoformat()),
        )
    return _a_seguimiento(
        conexion.execute("SELECT * FROM seguimientos WHERE id = ?", (cursor.lastrowid,)).fetchone()
    )


def seguimientos(conexion: sqlite3.Connection) -> list[Seguimiento]:
    return [
        _a_seguimiento(f) for f in conexion.execute("SELECT * FROM seguimientos ORDER BY id")
    ]


def dejar_de_seguir(conexion: sqlite3.Connection, identificador: int) -> bool:
    with conexion:
        cursor = conexion.execute("DELETE FROM seguimientos WHERE id = ?", (identificador,))
    return cursor.rowcount > 0


def anotar_revision(
    conexion: sqlite3.Connection,
    seguimiento: Seguimiento,
    mejor: Oferta | None,
    ahora: datetime | None = None,
) -> None:
    """Guarda el mejor precio hallado en esta revisión, para comparar con la próxima."""
    with conexion:
        if mejor is None:
            conexion.execute(
                "UPDATE seguimientos SET ultima_revision = ? WHERE id = ?",
                (_ahora(ahora).isoformat(), seguimiento.id),
            )
        else:
            conexion.execute(
                "UPDATE seguimientos SET ultimo_precio = ?, ultima_tienda = ?, ultima_url = ?,"
                " ultima_revision = ? WHERE id = ?",
                (mejor.precio, mejor.tienda, mejor.url, _ahora(ahora).isoformat(),
                 seguimiento.id),
            )


def abrir(ruta: Path | str | None = None):
    """Conexión que se cierra sola: `with historial.abrir() as conexion:`."""
    return closing(conectar(ruta))
