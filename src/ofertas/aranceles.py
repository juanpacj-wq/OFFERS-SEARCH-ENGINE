"""Arancel de importación de Colombia por categoría de producto.

Fuente: Banco Mundial, WITS (https://wits.worldbank.org), datos TRAINS reportados por
Colombia. Es el promedio simple del arancel de nación más favorecida para la subpartida
de seis dígitos del Sistema Armonizado. Los valores de la tabla se consultaron el
2026-11-19 y corresponden a 2023; `actualizar` los vuelve a traer y los guarda en la
base local, donde tienen prioridad sobre la tabla.

El arancel real de una importación puede ser menor (acuerdos comerciales según el
país de origen) y se cobra sobre el valor con flete y seguro. Aquí sirve para estimar
cuánto más es razonable que cueste un producto en Colombia que afuera.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from ofertas import identidad
from ofertas.conectores.base import ErrorTienda, leer_json, pedir

URL_WITS = (
    "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN/reporter/170/partner/000"
    "/product/{hs}/year/{anio}/datatype/reported?format=JSON"
)
ANIO_DE_LA_TABLA = 2023
# Cuántos años hacia atrás se prueba al actualizar (la base publica con rezago).
ANIOS_A_PROBAR = 4


@dataclass(frozen=True)
class Categoria:
    nombre: str
    hs: str
    arancel: float  # fracción: 0.15 es 15%
    palabras: tuple[str, ...]


# El orden no importa: gana la palabra que aparece primero en el nombre del producto.
CATEGORIAS: tuple[Categoria, ...] = (
    Categoria("computadores portátiles y tabletas", "847130", 0.0,
              ("portatil", "portatiles", "laptop", "notebook", "computador", "tablet", "ipad",
               "macbook", "chromebook")),
    Categoria("celulares", "851712", 0.0,
              ("celular", "celulares", "smartphone", "iphone", "telefono")),
    Categoria("televisores", "852872", 0.11, ("televisor", "televisores", "tv", "smarttv")),
    Categoria("monitores", "852852", 0.0, ("monitor", "monitores")),
    Categoria("audífonos", "851830", 0.0, ("audifonos", "audifono", "auriculares", "airpods")),
    Categoria("parlantes", "851822", 0.0, ("parlante", "parlantes", "altavoz", "soundbar")),
    Categoria("relojes inteligentes", "851762", 0.0, ("smartwatch", "smartband")),
    Categoria("cámaras", "852580", 0.0, ("camara", "camaras")),
    Categoria("impresoras", "844332", 0.0, ("impresora", "impresoras")),
    Categoria("consolas de videojuegos", "950450", 0.15,
              ("consola", "playstation", "xbox", "nintendo")),
    Categoria("neveras", "841810", 0.15, ("nevera", "neveras", "refrigerador", "nevecon")),
    Categoria("lavadoras", "845020", 0.10, ("lavadora", "lavadoras", "secadora")),
    Categoria("estufas", "732111", 0.15, ("estufa", "estufas")),
    Categoria("hornos microondas", "851650", 0.05, ("microondas",)),
    Categoria("aires acondicionados", "841510", 0.033, ("aire", "minisplit")),
    Categoria("aspiradoras", "850811", 0.15, ("aspiradora", "aspiradoras")),
    Categoria("licuadoras y pequeños electrodomésticos", "850940", 0.15,
              ("licuadora", "batidora", "freidora", "cafetera")),
    Categoria("herramientas eléctricas", "846721", 0.0,
              ("taladro", "taladros", "atornillador", "pulidora", "esmeril", "rotomartillo")),
    Categoria("calzado deportivo", "640411", 0.15,
              ("tenis", "zapatillas", "guayos", "sneakers")),
    Categoria("calzado", "640399", 0.15, ("zapatos", "zapato", "botas", "botines", "mocasines")),
    Categoria("camisetas", "610910", 0.40, ("camiseta", "camisetas", "polo", "esqueleto")),
    Categoria("camisas", "620520", 0.40, ("camisa", "camisas", "blusa", "blusas")),
    Categoria("pantalones", "620342", 0.40,
              ("pantalon", "pantalones", "jean", "jeans", "bermuda", "short", "shorts",
               "pantaloneta", "sudadera", "leggings")),
    Categoria("chaquetas", "620193", 0.40,
              ("chaqueta", "chaquetas", "abrigo", "buzo", "buzos", "hoodie", "saco")),
    Categoria("morrales y maletas", "420292", 0.15,
              ("morral", "morrales", "maleta", "maletas", "bolso", "mochila", "maletin")),
    Categoria("relojes", "910211", 0.05, ("reloj", "relojes")),
    Categoria("bicicletas", "871200", 0.15, ("bicicleta", "bicicletas")),
    Categoria("juguetes", "950300", 0.15, ("juguete", "juguetes", "lego", "muneca", "peluche")),
    Categoria("colchones", "940429", 0.15, ("colchon", "colchones")),
    Categoria("sillas y muebles", "940171", 0.15,
              ("silla", "sillas", "sofa", "butaco", "escritorio", "mesa")),
    Categoria("perfumes", "330300", 0.15, ("perfume", "perfumes", "colonia", "locion")),
)
_POR_PALABRA = {palabra: c for c in CATEGORIAS for palabra in c.palabras}


def categoria_de(nombre: str) -> Categoria | None:
    """La categoría del producto, según la primera palabra clave de su nombre."""
    for palabra in identidad.palabras(nombre):
        if palabra in _POR_PALABRA:
            return _POR_PALABRA[palabra]
    return None


def arancel_de(nombre: str, conexion: sqlite3.Connection | None = None) -> tuple[float, str] | None:
    """Arancel y descripción de su fuente para un producto, o None si no se reconoce.

    Si la base local tiene un valor actualizado para la subpartida, se usa ese.
    """
    categoria = categoria_de(nombre)
    if categoria is None:
        return None
    arancel, anio = categoria.arancel, ANIO_DE_LA_TABLA
    if conexion is not None:
        fila = conexion.execute(
            "SELECT valor FROM ajustes WHERE clave = ?", (f"arancel:{categoria.hs}",)
        ).fetchone()
        try:
            guardado = json.loads(fila["valor"]) if fila else None
        except ValueError:
            guardado = None
        if guardado:
            arancel, anio = guardado["arancel"], guardado["anio"]
    fuente = f"arancel de {arancel * 100:.0f}% para {categoria.nombre} (Banco Mundial WITS, {anio})"
    return arancel, fuente


async def actualizar(cliente: httpx.AsyncClient, conexion: sqlite3.Connection) -> list[dict]:
    """Vuelve a consultar en WITS el arancel de cada categoría y lo guarda en la base."""
    resultados = []
    ultimo = datetime.now(UTC).year - 1
    for categoria in CATEGORIAS:
        hallado = None
        for anio in range(ultimo, ultimo - ANIOS_A_PROBAR, -1):
            try:
                datos = leer_json(await pedir(
                    cliente, URL_WITS.format(hs=categoria.hs, anio=anio),
                    headers={"Accept": "application/json"},
                ))
                series = datos["dataSets"][0]["series"]
                valor = next(iter(next(iter(series.values()))["observations"].values()))[0]
                hallado = {"arancel": round(float(valor) / 100, 4), "anio": anio}
                break
            except (ErrorTienda, KeyError, IndexError, StopIteration, TypeError, ValueError):
                continue  # ese año no está publicado: se prueba el anterior
        if hallado:
            with conexion:
                conexion.execute(
                    "INSERT INTO ajustes (clave, valor) VALUES (?, ?)"
                    " ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
                    (f"arancel:{categoria.hs}", json.dumps(hallado)),
                )
        resultados.append({
            "categoria": categoria.nombre, "hs": categoria.hs,
            "tabla": categoria.arancel, "actual": hallado,
        })
    return resultados
