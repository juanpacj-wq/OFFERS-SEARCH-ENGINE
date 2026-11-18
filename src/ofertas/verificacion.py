"""Une las piezas: agrupa las ofertas por producto, investiga afuera y emite el veredicto."""

from __future__ import annotations

import sqlite3

from ofertas import identidad, internacional, motor, veredicto
from ofertas.conectores import navegador
from ofertas.identidad import Grupo
from ofertas.modelos import Oferta, Resultado
from ofertas.tiendas import seleccionar

# En modo profundo, cuántas fichas técnicas distintas se salen a buscar en las tiendas.
FICHAS_A_AMPLIAR = 2
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
    fichas = {id(o): identidad.ficha_de(o) for o in resultado.ofertas}
    # Equipos de otras marcas con la misma ficha: los de esta búsqueda y, en modo
    # profundo, los que se salgan a buscar aparte.
    universo = list(resultado.ofertas)
    if profundo:
        ampliacion = await _buscar_por_ficha(grupos, fichas, referencias, transporte)
        for oferta in ampliacion:
            fichas[id(oferta)] = identidad.ficha_de(oferta)
        universo += ampliacion
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
            if juicio.clase == "sin_referencia":
                # Sin nada mejor, orienta el precio de otros equipos con la misma ficha.
                comparables = identidad.comparables_por_ficha(
                    oferta, universo, fichas, del_grupo
                )
                if comparables:
                    juicio = veredicto.evaluar(
                        oferta, otras, oferta.historial, referencia, variantes, comparables
                    )
            datos = juicio.a_dict()
            datos["coincidencia_entre_tiendas"] = grupo.via
            if referencia:
                datos["internacional"] = {
                    "precio_usd": referencia.precio_usd,
                    "trm": referencia.trm,
                    "en_pesos": round(referencia.en_pesos),
                    "con_iva": round(referencia.con_iva),
                    "tope_normal": round(referencia.tope_normal),
                    "margen_importacion": referencia.margen,
                    "coincidencia": referencia.coincidencia,
                    "ejemplo": referencia.ejemplo,
                    "url": referencia.url,
                    "fuentes": referencia.fuentes,
                }
            oferta.veredicto = datos
    _agregar_contexto(resultado.ofertas)
    return grupos, avisos


# Ofertas comprobadas que hacen falta para hablar de una proporción.
MIN_PARA_PROPORCION = 5


def proporcion_de_reales(ofertas: list[Oferta]) -> tuple[int, int] | None:
    """Cuántas de las ofertas con descuento anunciado que sí se comprobaron eran reales.

    Solo cuentan las comprobadas con evidencia firme (no aproximada). Devuelve
    (reales, comprobadas), o None si son muy pocas para decir algo.
    """
    comprobadas = [
        o.veredicto for o in ofertas
        if o.veredicto
        and o.descuento_pct >= veredicto.DESCUENTO_ANUNCIADO_MINIMO
        and o.veredicto["clase"] != "sin_referencia"
        and o.veredicto["confianza"] != "aproximada"
    ]
    if len(comprobadas) < MIN_PARA_PROPORCION:
        return None
    reales = sum(1 for v in comprobadas if v["clase"] == "descuento_real")
    return reales, len(comprobadas)


def _agregar_contexto(ofertas: list[Oferta]) -> None:
    """A lo que no se pudo comprobar le suma cómo salieron las ofertas que sí se comprobaron.

    No es un veredicto sobre esa oferta: es el contexto para decidir cuánto creerle a un
    descuento que nadie más permite verificar.
    """
    proporcion = proporcion_de_reales(ofertas)
    if proporcion is None:
        return
    reales, comprobadas = proporcion
    frase = (
        f" Como referencia: en esta búsqueda, de {comprobadas} ofertas con descuento anunciado"
        f" que sí se pudieron comprobar, {reales} eran descuentos reales."
    )
    for oferta in ofertas:
        juicio = oferta.veredicto
        if not juicio:
            continue
        juicio["comprobadas_en_la_busqueda"] = comprobadas
        juicio["reales_en_la_busqueda"] = reales
        anuncia = oferta.descuento_pct >= veredicto.DESCUENTO_ANUNCIADO_MINIMO
        if juicio["clase"] == "sin_referencia" and anuncia:
            juicio["texto"] += frase


async def _buscar_por_ficha(
    grupos: list[Grupo],
    fichas: dict[int, identidad.Ficha | None],
    referencias: dict[int, veredicto.Internacional],
    transporte=None,
) -> list[Oferta]:
    """Busca en las tiendas computadores con el procesador de los productos sin referencia.

    Un portátil de configuración regional que solo vende una tienda no tiene con qué
    compararse; sí se puede saber cuánto cuestan otros equipos con su mismo procesador,
    memoria y almacenamiento. Es una búsqueda completa por ficha, así que se limita.
    """
    procesadores: list[str] = []
    for grupo in ordenar_para_informe(grupos):
        duenos = {identidad.familia(o.tienda_id) for o in grupo.ofertas}
        if id(grupo) in referencias or len(duenos) > 1:
            continue
        ficha = fichas.get(id(grupo.principal))
        if ficha and ficha.procesador not in procesadores:
            procesadores.append(ficha.procesador)
    halladas: list[Oferta] = []
    for procesador in procesadores[:FICHAS_A_AMPLIAR]:
        consulta = f"portatil {identidad.procesador_legible(procesador)}"
        try:
            ampliado = await motor.buscar(
                consulta, seleccionar(None), limite_por_tienda=40, transporte=transporte
            )
        except Exception:
            continue  # es un complemento: si falla, el informe sigue sin esa evidencia
        halladas += ampliado.ofertas
    return halladas


def resumen(ofertas: list[Oferta]) -> dict[str, int]:
    """Cuenta los veredictos de las ofertas que anuncian descuento."""
    conteo: dict[str, int] = {}
    for oferta in ofertas:
        if oferta.veredicto and oferta.descuento_pct >= veredicto.DESCUENTO_ANUNCIADO_MINIMO:
            clase = oferta.veredicto["clase"]
            conteo[clase] = conteo.get(clase, 0) + 1
    return conteo
