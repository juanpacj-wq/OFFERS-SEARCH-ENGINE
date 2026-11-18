"""Investigación del precio internacional de un producto.

Los códigos de barras de lo que se vende en Colombia casi nunca existen en las bases de
otros países (los modelos son regionales), así que el producto se busca afuera por
marca, familia y especificaciones, y cada resultado se califica según qué tan seguro es
que sea el mismo artículo:

- "exacto": mismo código de barras o mismo número de artículo del fabricante.
- "modelo": mismo código de modelo (tolerando el sufijo regional).
- "equivalente": misma marca, familia y especificaciones, pero no se puede asegurar que
  sea idéntico. Sirve de orientación, no de prueba.

Todo lo consultado se guarda siete días en la base local, de modo que repetir una
búsqueda no vuelve a preguntar afuera.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from statistics import median
from urllib.parse import quote

import httpx

from ofertas import identidad
from ofertas.conectores.base import ErrorTienda, a_numero, leer_json, pedir
from ofertas.identidad import Grupo
from ofertas.veredicto import IVA, Internacional

VIGENCIA_CACHE = timedelta(days=7)
# UPCitemdb (plan gratuito) rechaza consultas seguidas: hay que espaciarlas.
PAUSA_UPC_SEGUNDOS = 13
# Ofertas de comercios con más antigüedad que esto no se toman como precio vigente.
VIGENCIA_OFERTA_UPC = timedelta(days=540)
# El precio de afuera (con IVA) debe parecerse al local; si no, es otro producto.
RAZON_MINIMA, RAZON_MAXIMA = 0.35, 2.5
COBERTURA_MINIMA = 0.6
# Palabras del nombre (sin la marca) que deben coincidir para llamarlo equivalente.
MIN_PALABRAS_COMUNES = 2
# Desde este largo, un código de modelo suele llevar sufijo de país.
LARGO_MODELO_REGIONAL = 10
# Por debajo de este precio no vale la pena investigar afuera.
PRECIO_MINIMO_COP = 60000
ORDEN = {"exacto": 0, "modelo": 1, "equivalente": 2}

URL_TRM = "https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde%20DESC"
URL_TRM_RESPALDO = "https://open.er-api.com/v6/latest/USD"
URL_UPC = "https://api.upcitemdb.com/prod/trial/search?match_mode=0&type=product&s={q}"
URL_LENOVO = (
    "https://openapi.lenovo.com/us/en/ofp/search/global/cache/products/get/_tsc"
    "?fq=&text={q}&rows=15&sort=relevance&display_tab=Products"
)
URL_SAMSUNG = (
    "https://api.shop.samsung.com/tokocommercewebservices/v2/us/products/search"
    "?query={q}&pageSize=20&currentPage=0"
    "&fields=products(code,name,price(value)),pagination"
)
URL_BING = "https://www.bing.com/shop?q={q}&setmkt=en-US&setlang=en-US&cc=US"
# Si UPCitemdb responde que se excedió el límite, no se le vuelve a preguntar en este lapso.
CASTIGO_UPC_SEGUNDOS = 300
_RE_BING_TARJETA = re.compile(r'class="br-item')
_RE_BING_TITULO = re.compile(r'class="br-title[^"]*"[^>]*>\s*<span title="([^"]+)"')
_RE_BING_PRECIO = re.compile(r'class="pd-price[^"]*"[^>]*>.*?\$(\d[\d,]*(?:\.\d\d)?)', re.S)
_RE_BING_ENLACE = re.compile(r'class="br-titlelink[^"]*" href="([^"]+)"')
URL_IKEA = "https://sik.search.blue.cdtapps.com/us/en/search-result-page?q={q}&size=5&types=PRODUCT"


def _ahora() -> datetime:
    return datetime.now(UTC)


# --- caché y ajustes en la base local ---------------------------------------


def _leer_ajuste(conexion: sqlite3.Connection, clave: str) -> dict | None:
    fila = conexion.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
    try:
        return json.loads(fila["valor"]) if fila else None
    except ValueError:
        return None


def _guardar_ajuste(conexion: sqlite3.Connection, clave: str, valor: dict) -> None:
    with conexion:
        conexion.execute(
            "INSERT INTO ajustes (clave, valor) VALUES (?, ?)"
            " ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
            (clave, json.dumps(valor)),
        )


def _leer_cache(conexion: sqlite3.Connection, fuente: str, consulta: str) -> list[dict] | None:
    fila = conexion.execute(
        "SELECT fecha, datos FROM cache_internacional WHERE fuente = ? AND consulta = ?",
        (fuente, consulta),
    ).fetchone()
    if not fila or _ahora() - datetime.fromisoformat(fila["fecha"]) > VIGENCIA_CACHE:
        return None
    try:
        return json.loads(fila["datos"])
    except ValueError:
        return None


def _guardar_cache(
    conexion: sqlite3.Connection, fuente: str, consulta: str, datos: list[dict]
) -> None:
    with conexion:
        conexion.execute(
            "INSERT INTO cache_internacional (fuente, consulta, fecha, datos) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (fuente, consulta) DO UPDATE SET"
            " fecha = excluded.fecha, datos = excluded.datos",
            (fuente, consulta, _ahora().isoformat(), json.dumps(datos, ensure_ascii=False)),
        )


# --- tasa de cambio ---------------------------------------------------------


async def obtener_trm(cliente: httpx.AsyncClient, conexion: sqlite3.Connection) -> float | None:
    """TRM oficial del día (datos.gov.co), con respaldo y con la última conocida."""
    hoy = _ahora().date().isoformat()
    guardada = _leer_ajuste(conexion, "trm")
    if guardada and guardada.get("fecha") == hoy:
        return guardada["valor"]
    valor = None
    try:
        filas = leer_json(await pedir(cliente, URL_TRM))
        valor = a_numero(filas[0]["valor"]) if filas else None
    except (ErrorTienda, KeyError, IndexError, TypeError):
        pass
    if not valor:
        try:
            valor = a_numero(leer_json(await pedir(cliente, URL_TRM_RESPALDO))["rates"]["COP"])
        except (ErrorTienda, KeyError, TypeError):
            valor = None
    if valor and valor > 0:
        _guardar_ajuste(conexion, "trm", {"fecha": hoy, "valor": valor})
        return valor
    return guardada["valor"] if guardada else None


# --- qué buscar afuera ------------------------------------------------------


def consulta_para(grupo: Grupo) -> str:
    """Arma la búsqueda internacional: marca, familia y capacidad, sin códigos regionales."""
    principal = grupo.principal
    codigos = {m.lower() for m in grupo.modelos}
    marca = grupo.marca
    nombre = identidad.sin_procesador(principal.nombre)
    palabras = [
        p for p in identidad.distintivos(nombre, marca)
        if p not in codigos and not (p.isdigit() and len(p) > 4)
    ]
    if marca and marca in palabras:
        palabras.remove(marca)
    capacidades = sorted(
        (m for m in identidad.medidas(principal.nombre) if m.endswith(("gb", "tb"))),
        key=lambda m: float(m[:-2]) * (1024 if m.endswith("tb") else 1),
    )
    partes = ([marca] if marca else []) + palabras[:4] + capacidades[-1:]
    return " ".join(partes)


def consulta_por_modelo(grupo: Grupo) -> str | None:
    """El modelo sin su sufijo de país: "UN55CU7000KXZL" se busca como "UN55CU7000".

    Afuera el mismo producto lleva otro sufijo (FXZA en EE. UU.), así que el prefijo es
    la forma más precisa de encontrarlo. Solo aplica a códigos largos.
    """
    largos = sorted((m for m in grupo.modelos if len(m) >= LARGO_MODELO_REGIONAL), key=len)
    if not largos:
        return None
    modelo = largos[-1]
    return modelo[: max(8, len(modelo) - 4)]


def consultas_generales(grupo: Grupo) -> list[str]:
    """Consultas para un buscador de comercios, de la más precisa a la más amplia.

    Primero la marca con el modelo (sin sufijo de país si es largo); si eso no da nada,
    la marca con la familia, la capacidad y el procesador.
    """
    marca = grupo.marca
    consultas = []
    modelos = sorted(grupo.modelos, key=len)
    if modelos:
        modelo = consulta_por_modelo(grupo) or modelos[-1]
        consultas.append(f"{marca} {modelo}".strip())
    procesador = identidad.procesador(grupo.principal.nombre)
    legible = {"intel": "core i", "ryzen": "ryzen "}
    cpu = next(
        (f"{legible[k]}{procesador[len(k):]}" for k in legible if procesador.startswith(k)), ""
    )
    consultas.append(f"{consulta_para(grupo)} {cpu}".strip())
    return consultas


def vale_la_pena(grupo: Grupo) -> bool:
    """Descarta lo que no tiene sentido comparar afuera: barato o sin marca reconocible."""
    if grupo.precio_mediano < PRECIO_MINIMO_COP:
        return False
    return bool(grupo.marca) and len(consulta_para(grupo).split()) >= 2


# --- calificación de candidatos ---------------------------------------------


def vocabulario_de(candidatos: list[dict]) -> frozenset[str]:
    """Todas las palabras que aparecen en los títulos de un lote de candidatos."""
    return frozenset(p for c in candidatos for p in identidad.palabras(c.get("titulo") or ""))


def calificar(
    grupo: Grupo, candidato: dict, trm: float, vocabulario: frozenset[str] | None = None
) -> tuple[str, float] | None:
    """Dice qué tan seguro es que el candidato sea el producto del grupo, o None si no lo es.

    `vocabulario` son las palabras del lote de resultados de afuera. Los nombres de aquí
    traen palabras en español ("fotográfica", "inalámbrico") que jamás aparecen en un
    título en inglés; para no castigar eso, la coincidencia se mide solo con las palabras
    del nombre que existen en ese vocabulario (marcas, líneas y números, que no cambian).
    """
    precio = a_numero(candidato.get("precio_usd"))
    if precio <= 0:
        return None
    titulo = candidato.get("titulo") or ""
    razon = precio * trm * (1 + IVA) / grupo.precio_mediano
    if not RAZON_MINIMA <= razon <= RAZON_MAXIMA:
        return None
    principal = grupo.principal
    if identidad.es_usado(titulo) != identidad.es_usado(principal.nombre):
        return None

    ean = str(candidato.get("ean") or "").lstrip("0")
    if candidato.get("exacto") or (ean and ean in {e.lstrip("0") for e in grupo.eans}):
        return "exacto", 1.0
    codigos = identidad.codigos_de_modelo(titulo)
    if candidato.get("codigo"):
        codigos.add(str(candidato["codigo"]).upper())
    # Con el mismo código de modelo es el mismo producto aunque los nombres difieran,
    # salvo que el anuncio solo lo mencione ("control para...", "paquete con...").
    de_la_marca = bool(candidato.get("de_marca"))
    if (de_la_marca or not identidad.menciona_sin_ser(titulo)) and any(
        identidad.mismo_modelo(a, b) or identidad.variante_regional(a, b)
        for a in grupo.modelos
        for b in codigos
    ):
        return "modelo", 1.0
    if identidad.es_accesorio(titulo) != identidad.es_accesorio(principal.nombre):
        return None
    # Afuera el modelo suele venir sin prefijo ni sufijo regional: "CU7000" es el
    # "UN55CU7000KXZL" de Colombia. Vale si además coincide el tamaño.
    tamanos_local = {m for m in identidad.medidas(principal.nombre) if m.endswith("in")}
    tamanos_afuera = {m for m in identidad.medidas(titulo) if m.endswith("in")}
    mismo_tamano = not (tamanos_local and tamanos_afuera) or bool(tamanos_local & tamanos_afuera)
    if mismo_tamano and any(
        identidad.modelo_contenido(a, b) for a in grupo.modelos for b in codigos
    ):
        return "modelo", 0.9

    palabras_candidato = set(identidad.palabras(titulo))
    marca = grupo.marca
    if marca and marca not in identidad.normalizar(titulo) and not candidato.get("de_marca"):
        return None
    propias = [
        p for p in identidad.distintivos(principal.nombre, "")
        if p != marca and p not in {m.lower() for m in grupo.modelos}
    ]
    if vocabulario is not None:
        propias = [p for p in propias if p in vocabulario]
    # Con una sola palabra en común ("galaxy") no se puede afirmar que sea equivalente.
    if len(propias) < MIN_PALABRAS_COMUNES:
        return None
    # Las variantes deben coincidir en ambos sentidos: un S25 no es un S25 Ultra.
    variantes = identidad.VARIANTES
    if variantes.intersection(propias) != variantes.intersection(palabras_candidato):
        return None
    # Si el candidato dice memoria o capacidad, debe traer todas las del producto local;
    # si dice tamaño, debe ser el mismo. Y el procesador, si ambos lo dicen, igual.
    medidas_locales = identidad.medidas(principal.nombre)
    medidas_afuera = identidad.medidas(titulo)
    for unidades in (("gb", "tb"), ("in",)):
        locales = {m for m in medidas_locales if m.endswith(unidades)}
        afuera = {m for m in medidas_afuera if m.endswith(unidades)}
        if locales and afuera and not identidad.medidas_compatibles(locales, afuera):
            return None
    cpu_local, cpu_afuera = identidad.procesador(principal.nombre), identidad.procesador(titulo)
    if cpu_local and cpu_afuera and cpu_local != cpu_afuera:
        return None
    cobertura = sum(1 for p in propias if p in palabras_candidato) / len(propias)
    if cobertura < COBERTURA_MINIMA:
        return None
    return "equivalente", cobertura


def resumir(grupo: Grupo, candidatos: list[dict], trm: float) -> Internacional | None:
    """Convierte los candidatos válidos en una referencia: la mediana de los más seguros."""
    calificados = []
    vocabulario = vocabulario_de(candidatos)
    for candidato in candidatos:
        nota = calificar(grupo, candidato, trm, vocabulario)
        if nota:
            calificados.append((ORDEN[nota[0]], -nota[1], nota[0], candidato))
    if not calificados:
        return None
    calificados.sort(key=lambda c: (c[0], c[1]))
    mejor_clase = calificados[0][2]
    elegidos = [c[3] for c in calificados if c[2] == mejor_clase]
    if mejor_clase == "equivalente":
        # Entre equivalentes solo cuentan los que mejor coinciden con el nombre.
        tope = -calificados[0][1]
        elegidos = [c[3] for c in calificados if c[2] == mejor_clase and -c[1] >= tope - 0.15]
    return Internacional(
        precio_usd=round(median(a_numero(c["precio_usd"]) for c in elegidos), 2),
        trm=trm,
        coincidencia=mejor_clase,
        fuentes=sorted({c["fuente"] for c in elegidos}),
        ejemplo=elegidos[0].get("titulo") or "",
        url=elegidos[0].get("url") or "",
        candidatos=len(elegidos),
    )


# --- fuentes ----------------------------------------------------------------


def _sin_marca(consulta: str, marca: str) -> str:
    return " ".join(p for p in consulta.split() if p != marca) or consulta


async def fuente_lenovo(cliente: httpx.AsyncClient, grupo: Grupo, consulta: str) -> list[dict]:
    respuesta = await pedir(
        cliente, URL_LENOVO.format(q=quote(_sin_marca(consulta, "lenovo"), safe="")),
        headers={"Referer": "https://www.lenovo.com/us/en/", "Origin": "https://www.lenovo.com"},
    )
    cuerpo = (leer_json(respuesta) or {}).get("data") or {}
    salida = []
    for bloque in cuerpo.get("data") or []:
        for producto in bloque.get("products") or []:
            if producto.get("currencyCode") not in (None, "USD"):
                continue
            salida.append({
                "fuente": "Lenovo EE. UU.",
                "titulo": f"Lenovo {producto.get('summary') or producto.get('description') or ''}",
                "precio_usd": a_numero(producto.get("finalPrice")),
                "url": f"https://www.lenovo.com/us/en{producto.get('url') or ''}",
                "codigo": producto.get("productCode"),
                "de_marca": True,
            })
    return salida


async def fuente_samsung(cliente: httpx.AsyncClient, grupo: Grupo, consulta: str) -> list[dict]:
    respuesta = await pedir(
        cliente, URL_SAMSUNG.format(q=quote(_sin_marca(consulta, "samsung"), safe=""))
    )
    salida = []
    for producto in (leer_json(respuesta) or {}).get("products") or []:
        codigo = producto.get("code") or ""
        salida.append({
            "fuente": "Samsung EE. UU.",
            "titulo": f"Samsung {producto.get('name') or ''}",
            "precio_usd": a_numero((producto.get("price") or {}).get("value")),
            "url": f"https://www.samsung.com/us/search/searchMain/?listType=g&searchTerm={codigo}",
            "codigo": codigo,
            "de_marca": True,
        })
    return salida


async def fuente_ikea(cliente: httpx.AsyncClient, grupo: Grupo, consulta: str) -> list[dict]:
    """IKEA usa el mismo número de artículo en todos los países: la coincidencia es exacta."""
    salida = []
    for numero in sorted(m for m in grupo.modelos if m.isdigit())[:2]:
        respuesta = await pedir(cliente, URL_IKEA.format(q=numero))
        principal = (
            (((leer_json(respuesta) or {}).get("searchResultPage") or {}).get("products") or {})
            .get("main") or {}
        )
        for elemento in principal.get("items") or []:
            producto = elemento.get("product") or {}
            venta = producto.get("salesPrice") or {}
            if producto.get("itemNoGlobal") != numero or venta.get("currencyCode") != "USD":
                continue
            salida.append({
                "fuente": "IKEA EE. UU.",
                "titulo": f"IKEA {producto.get('name')} {producto.get('typeName')}",
                "precio_usd": a_numero(venta.get("numeral")),
                "url": producto.get("pipUrl") or "",
                "codigo": numero,
                "exacto": True,
                "de_marca": True,
            })
    return salida


async def fuente_upcitemdb(cliente: httpx.AsyncClient, grupo: Grupo, consulta: str) -> list[dict]:
    """Comercios de EE. UU. por búsqueda de texto. Usa la mediana de ofertas vigentes."""
    try:
        respuesta = await pedir(cliente, URL_UPC.format(q=quote(consulta, safe="")))
    except ErrorTienda as exc:
        if "HTTP 404" in str(exc):
            return []  # así responde cuando la búsqueda no encuentra nada
        raise
    limite = time.time() - VIGENCIA_OFERTA_UPC.total_seconds()
    salida = []
    for item in (leer_json(respuesta) or {}).get("items") or []:
        precios = [
            a_numero(o.get("price"))
            for o in item.get("offers") or []
            if (o.get("condition") or "New") == "New"
            and a_numero(o.get("price")) > 0
            and a_numero(o.get("updated_t")) >= limite
        ]
        if not precios:
            continue
        salida.append({
            "fuente": "Comercios de EE. UU. (UPCitemdb)",
            "titulo": item.get("title") or "",
            "precio_usd": round(median(precios), 2),
            "url": f"https://www.upcitemdb.com/upc/{item.get('ean') or item.get('upc') or ''}",
            "codigo": item.get("model"),
            "ean": item.get("ean"),
        })
    return salida


async def fuente_bing(cliente: httpx.AsyncClient, grupo: Grupo, consulta: str) -> list[dict]:
    """Bing Shopping para EE. UU.: comercios de todo tipo, cualquier marca, en dólares."""
    respuesta = await pedir(
        cliente, URL_BING.format(q=quote(consulta, safe="")),
        headers={"Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"},
    )
    salida = []
    for trozo in _RE_BING_TARJETA.split(respuesta.text)[1:]:
        titulo, precio = _RE_BING_TITULO.search(trozo), _RE_BING_PRECIO.search(trozo)
        if not (titulo and precio):
            continue
        enlace = _RE_BING_ENLACE.search(trozo)
        salida.append({
            "fuente": "Bing Shopping (comercios de EE. UU.)",
            "titulo": html.unescape(titulo.group(1)),
            "precio_usd": a_numero(precio.group(1).replace(",", "")),
            "url": "https://www.bing.com" + html.unescape(enlace.group(1)) if enlace else "",
        })
    return salida


async def _bing(
    cliente: httpx.AsyncClient, conexion: sqlite3.Connection, grupo: Grupo, trm: float
) -> tuple[list[dict], str | None]:
    """Prueba las consultas generales en orden y se queda con la primera que sirva."""
    candidatos: list[dict] = []
    aviso = None
    for consulta in consultas_generales(grupo):
        hallados, aviso = await _consultar(cliente, conexion, "bing", fuente_bing, grupo, consulta)
        candidatos += hallados
        vocabulario = vocabulario_de(hallados)
        if any(calificar(grupo, c, trm, vocabulario) for c in hallados):
            break
    return candidatos, aviso


FUENTES_DE_MARCA = {"lenovo": fuente_lenovo, "samsung": fuente_samsung, "ikea": fuente_ikea}


async def _consultar(
    cliente: httpx.AsyncClient,
    conexion: sqlite3.Connection,
    nombre: str,
    fuente,
    grupo: Grupo,
    consulta: str,
) -> tuple[list[dict], str | None]:
    """Corre una fuente con caché. Devuelve los candidatos y, si falló, el motivo."""
    clave = consulta if nombre != "ikea" else " ".join(sorted(grupo.modelos))
    guardados = _leer_cache(conexion, nombre, clave)
    if guardados is not None:
        return guardados, None
    try:
        candidatos = await fuente(cliente, grupo, consulta)
    except ErrorTienda as exc:
        return [], f"{nombre}: {exc}"
    except Exception as exc:
        return [], f"{nombre}: respuesta con formato inesperado ({type(exc).__name__})"
    _guardar_cache(conexion, nombre, clave, candidatos)
    return candidatos, None


async def _upc_con_pausa(
    cliente: httpx.AsyncClient,
    conexion: sqlite3.Connection,
    grupo: Grupo,
    consulta: str,
    esperar: bool,
) -> tuple[list[dict], str | None]:
    """UPCitemdb respetando su límite: espera si se le permite, o lo deja para después."""
    if _leer_cache(conexion, "upcitemdb", consulta) is None:
        estado = _leer_ajuste(conexion, "ultimo_upc") or {}
        if time.time() < estado.get("castigado_hasta", 0):
            return [], None  # ya dijo que se excedió el límite: no se insiste
        falta = PAUSA_UPC_SEGUNDOS - (time.time() - estado.get("momento", 0))
        if falta > 0:
            if not esperar:
                return [], None  # en una búsqueda normal no se espera: queda para después
            await asyncio.sleep(falta)
        _guardar_ajuste(conexion, "ultimo_upc", {"momento": time.time()})
    candidatos, aviso = await _consultar(
        cliente, conexion, "upcitemdb", fuente_upcitemdb, grupo, consulta
    )
    if aviso and "HTTP 429" in aviso:
        _guardar_ajuste(conexion, "ultimo_upc", {
            "momento": time.time(), "castigado_hasta": time.time() + CASTIGO_UPC_SEGUNDOS,
        })
        aviso = "UPCitemdb alcanzó su límite de consultas; se usaron las demás fuentes."
    return candidatos, aviso


async def investigar(
    cliente: httpx.AsyncClient,
    conexion: sqlite3.Connection,
    grupos: list[Grupo],
    *,
    profundo: bool = False,
    extra: dict[int, list[dict]] | None = None,
) -> tuple[dict[int, Internacional], list[str]]:
    """Busca el precio internacional de cada grupo.

    Devuelve las referencias por `id(grupo)` y la lista de avisos (fuentes que fallaron).
    Para cada producto se consultan a la vez la tienda de su marca, si la hay, y Bing
    Shopping. UPCitemdb, que es lento, solo se usa en modo profundo y para lo que las
    otras fuentes no resolvieron. `extra` permite sumar candidatos de otra fuente ya
    consultada (Amazon por navegador).
    """
    trm = await obtener_trm(cliente, conexion)
    if not trm:
        return {}, ["No se pudo obtener la TRM; se omitió la comparación internacional."]
    referencias: dict[int, Internacional] = {}
    avisos: list[str] = []
    pendientes_upc: list[tuple[Grupo, str, list[dict]]] = []

    async def de_marca(grupo: Grupo) -> tuple[Grupo, str, list[dict]]:
        consulta = consulta_para(grupo)
        por_modelo = consulta_por_modelo(grupo)
        candidatos = list((extra or {}).get(id(grupo), []))
        fuente = FUENTES_DE_MARCA.get(grupo.marca)
        if fuente:
            consultas = [consulta] if grupo.marca == "ikea" else [por_modelo, consulta]
            for hallados, aviso in await asyncio.gather(
                *(_consultar(cliente, conexion, grupo.marca, fuente, grupo, c)
                  for c in consultas if c)
            ):
                candidatos += hallados
                if aviso and aviso not in avisos:
                    avisos.append(aviso)
        elif por_modelo:
            # Sin tienda de marca, lo más preciso para los comercios es el modelo.
            consulta = por_modelo
        # Si la tienda de la marca ya dio el mismo producto, no hace falta preguntar más.
        previa = resumir(grupo, candidatos, trm)
        if not (previa and previa.confiable):
            hallados, aviso = await _bing(cliente, conexion, grupo, trm)
            candidatos += hallados
            if aviso and aviso not in avisos:
                avisos.append(aviso)
        return grupo, consulta, candidatos

    for grupo, consulta, candidatos in await asyncio.gather(*(de_marca(g) for g in grupos)):
        referencia = resumir(grupo, candidatos, trm)
        if referencia:
            referencias[id(grupo)] = referencia
        if profundo and not (referencia and referencia.confiable):
            pendientes_upc.append((grupo, consulta, candidatos))

    # UPCitemdb va de a una consulta, solo en modo profundo y para lo no resuelto.
    for grupo, consulta, candidatos in pendientes_upc:
        hallados, aviso = await _upc_con_pausa(cliente, conexion, grupo, consulta, True)
        if aviso and aviso not in avisos:
            avisos.append(aviso)
        referencia = resumir(grupo, candidatos + hallados, trm)
        if referencia:
            referencias[id(grupo)] = referencia
    return referencias, avisos
