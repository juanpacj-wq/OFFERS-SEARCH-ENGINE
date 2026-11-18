"""Une las piezas: agrupa las ofertas por producto, investiga afuera y emite el veredicto."""

from __future__ import annotations

import sqlite3

from ofertas import identidad, internacional, motor, veredicto
from ofertas.conectores import navegador
from ofertas.identidad import Grupo
from ofertas.modelos import Oferta, Resultado
from ofertas.tiendas import seleccionar

# Cuántos productos distintos se investigan afuera en una búsqueda normal y en una profunda.
GRUPOS_NORMAL = 10
GRUPOS_PROFUNDO = 12


def ordenar_para_informe(grupos: list[Grupo]) -> list[Grupo]:
    """Primero los productos más verificables: en más tiendas y con mayor descuento anunciado."""
    return sorted(
        grupos,
        key=lambda g: (-len({o.tienda_id for o in g.ofertas}),
                       -max(o.descuento_pct for o in g.ofertas), g.precio_mediano),
    )


def _grupos_a_investigar(
    grupos: list[Grupo], ofertas: list[Oferta], mostradas: int, maximo: int
) -> list[Grupo]:
    """Los productos de las ofertas que se van a mostrar, en orden y sin repetir."""
    de_oferta = {id(o): g for g in grupos for o in g.ofertas}
    candidatos: list[Grupo] = []
    for oferta in ofertas[:mostradas]:
        grupo = de_oferta[id(oferta)]
        if grupo not in candidatos and internacional.vale_la_pena(grupo):
            candidatos.append(grupo)
    # Primero los que no tienen con qué compararse en Colombia: ahí el precio de afuera
    # es la única evidencia. sorted es estable, así que se conserva el orden mostrado.
    return sorted(candidatos, key=_tiene_mercado_local)[:maximo]


def _tiene_mercado_local(grupo: Grupo) -> bool:
    """Tres o más voces independientes: cualquier oferta tiene dos tiendas con qué compararse."""
    voces: set[str] = set()
    independientes = 0
    for oferta in sorted(grupo.ofertas, key=lambda o: o.precio):
        propias = identidad.voces(oferta)
        if not propias & voces:
            independientes += 1
        voces |= propias
    return independientes >= 3


async def _candidatos_de_amazon(grupos: list[Grupo], trm: float) -> dict[int, list[dict]]:
    """Busca cada producto en Amazon con el navegador y devuelve candidatos en dólares."""
    (amazon,) = seleccionar(["amazon"])
    salida: dict[int, list[dict]] = {}
    try:
        for grupo in grupos:
            try:
                ofertas, _, _ = await navegador.buscar(
                    None, amazon, internacional.consulta_para(grupo), 30
                )
            except Exception:
                continue  # Amazon es una fuente más: si falla, se sigue con las otras.
            salida[id(grupo)] = [
                {
                    "fuente": "Amazon (precio convertido a pesos por Amazon)",
                    "titulo": o.nombre,
                    "precio_usd": round(o.precio / trm, 2),
                    "url": o.url,
                }
                for o in ofertas
            ]
    finally:
        await navegador.cerrar()
    return salida


async def verificar(
    resultado: Resultado,
    conexion: sqlite3.Connection,
    *,
    mostradas: int = 20,
    con_internacional: bool = True,
    profundo: bool = False,
    con_amazon: bool = False,
    max_grupos: int | None = None,
    transporte=None,
) -> tuple[list[Grupo], list[str]]:
    """Pone en cada oferta su veredicto. Devuelve los grupos de producto y los avisos.

    En modo profundo se investigan afuera los `max_grupos` productos que encabezan el
    informe (hasta `GRUPOS_PROFUNDO`); en modo normal, los de las primeras ofertas.
    """
    grupos = identidad.agrupar(resultado.ofertas)
    referencias: dict[int, veredicto.Internacional] = {}
    avisos: list[str] = []
    if con_internacional:
        if profundo:
            tope = min(max_grupos or GRUPOS_PROFUNDO, GRUPOS_PROFUNDO)
            elegidos = [
                g for g in ordenar_para_informe(grupos) if internacional.vale_la_pena(g)
            ][:tope]
        else:
            elegidos = _grupos_a_investigar(grupos, resultado.ofertas, mostradas, GRUPOS_NORMAL)
        if elegidos:
            try:
                async with motor.crear_cliente(transporte) as cliente:
                    extra = None
                    if con_amazon:
                        trm = await internacional.obtener_trm(cliente, conexion)
                        extra = await _candidatos_de_amazon(elegidos, trm) if trm else None
                    referencias, avisos = await internacional.investigar(
                        cliente, conexion, elegidos, profundo=profundo, extra=extra
                    )
            except Exception as exc:
                # La investigación afuera es un complemento: si falla, queda el juicio local.
                avisos.append(f"No se pudo investigar el precio internacional ({exc}).")

    huellas = {id(o): identidad.huella_de(o) for o in resultado.ofertas}
    for grupo in grupos:
        referencia = referencias.get(id(grupo))
        del_grupo = {id(o) for o in grupo.ofertas}
        for oferta in grupo.ofertas:
            otras = grupo.otras_tiendas(oferta)
            # Las variantes solo se buscan si el producto idéntico no basta: cuesta comparar.
            variantes = (
                identidad.variantes_en_otras_tiendas(
                    oferta, resultado.ofertas, huellas, del_grupo
                )
                if len(otras) < 2
                else None
            )
            juicio = veredicto.evaluar(oferta, otras, oferta.historial, referencia, variantes)
            datos = juicio.a_dict()
            datos["coincidencia_entre_tiendas"] = grupo.via
            if referencia:
                datos["internacional"] = {
                    "precio_usd": referencia.precio_usd,
                    "trm": referencia.trm,
                    "en_pesos": round(referencia.en_pesos),
                    "con_iva": round(referencia.con_iva),
                    "tope_normal": round(referencia.tope_normal),
                    "coincidencia": referencia.coincidencia,
                    "ejemplo": referencia.ejemplo,
                    "url": referencia.url,
                    "fuentes": referencia.fuentes,
                }
            oferta.veredicto = datos
    return grupos, avisos


def resumen(ofertas: list[Oferta]) -> dict[str, int]:
    """Cuenta los veredictos de las ofertas que anuncian descuento."""
    conteo: dict[str, int] = {}
    for oferta in ofertas:
        if oferta.veredicto and oferta.descuento_pct >= veredicto.DESCUENTO_ANUNCIADO_MINIMO:
            clase = oferta.veredicto["clase"]
            conteo[clase] = conteo.get(clase, 0) + 1
    return conteo
