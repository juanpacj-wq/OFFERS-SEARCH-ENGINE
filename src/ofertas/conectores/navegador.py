"""Conector para tiendas que solo responden a un navegador de verdad.

Abre el Edge instalado en el equipo con un perfil propio del motor, carga la página
de búsqueda de la tienda y lee los resultados de la página ya dibujada.

Lo que NO hace, a propósito: no oculta que es un navegador automatizado, no altera
huellas ni resuelve captchas. Si una tienda muestra una verificación, el motor lo
reporta y la persona puede resolverla a mano con `ofertas navegador <tienda>`; la
sesión queda guardada en el perfil para las búsquedas siguientes.

Requiere el extra opcional: `uv sync --extra navegador`.
"""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ofertas.conectores.base import ErrorTienda, precio_de_texto
from ofertas.modelos import Oferta, Tienda

# Tiendas cuya URL no recibe la consulta completa sino el nombre de una marca.
POR_MARCA = {"meli_oficial"}
MAX_MARCAS = 4
PAUSA_MS = 1000
INTENTOS = 12
TIEMPO_CARGA_MS = 45000
_RE_RETO = re.compile(
    r"captcha|completa este paso|just a moment|access denied|verifica que eres", re.I
)

# Cada extractor corre dentro de la página y devuelve una lista de objetos con
# nombre, marca, precio, antes, url e imagen (los precios como texto, tal cual se ven).
EXTRACTORES: dict[str, str] = {
    "amazon": """() => [...document.querySelectorAll('div[data-component-type="s-search-result"]')].map(e => ({
        nombre: (e.querySelector('h2') || {}).innerText || '',
        marca: '',
        precio: (e.querySelector('.a-price:not(.a-text-price) .a-offscreen') || {}).textContent || '',
        antes: (e.querySelector('.a-price[data-a-strike="true"] .a-offscreen') || {}).textContent || '',
        url: e.dataset.asin ? location.origin + '/dp/' + e.dataset.asin : '',
        imagen: (e.querySelector('img.s-image') || {}).src || '',
    }))""",
    "meli_oficial": """() => [...document.querySelectorAll('.poly-card')].map(e => {
        const enlace = e.querySelector('a.poly-component__title');
        const monto = s => { const n = e.querySelector(s); return n ? '$ ' + n.textContent : ''; };
        return {
            nombre: enlace ? enlace.innerText : '',
            marca: '',
            precio: monto('.poly-price__current .andes-money-amount__fraction'),
            antes: monto('s.poly-price__previous .andes-money-amount__fraction'),
            url: enlace ? enlace.href.split('#')[0] : '',
            imagen: (e.querySelector('img') || {}).src || '',
        };
    })""",
    "decathlon": """() => [...document.querySelectorAll('.product-card')].map(e => {
        const enlace = e.querySelector('h2 a');
        return {
            nombre: enlace ? enlace.innerText : '',
            marca: '',
            precio: ((e.querySelector('.vp-price-amount') || {}).innerText || '').replace('Precio actual', ''),
            antes: ((e.querySelector('.vp-price-barred-amount') || {}).innerText || '').replace('Precio anterior', ''),
            url: enlace ? enlace.href : '',
            imagen: (e.querySelector('img') || {}).src || '',
        };
    })""",
    "dafiti": """() => [...document.querySelectorAll('.itm-product-main-info')].map(e => {
        const enlace = e.querySelector('a[href$=".html"]') || e.querySelector('a');
        const caja = e.querySelector('.itm-priceBox');
        const actual = caja ? parseFloat(caja.dataset.price) : NaN;
        return {
            nombre: (e.querySelector('.itm-title') || {}).innerText || '',
            marca: (e.querySelector('.itm-brand') || {}).innerText || '',
            // Sin rebaja, la tienda deja vacío el precio especial y solo trae el original.
            precio: isNaN(actual) ? (caja ? caja.dataset.originalprice || '' : '') : '$ ' + Math.round(actual),
            antes: caja ? (caja.dataset.originalprice || '') : '',
            url: enlace ? enlace.href : '',
            imagen: (e.querySelector('img') || {}).src || '',
        };
    })""",
}

# Extractor para tiendas sin uno propio: busca enlaces cuyo contenedor cercano muestre
# un precio y arma la tarjeta con el título, los precios visibles y la imagen.
# Devuelve `precios` (todos los que se ven) en lugar de `precio`.
GENERICO = r"""() => {
  const RE = /\$\s?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\$\s?\d{4,}/g;
  const vistos = new Set(), salida = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href;
    if (!href || href.startsWith('javascript') || vistos.has(href)) continue;
    let nodo = a, tarjeta = null;
    for (let i = 0; i < 6 && nodo; i++, nodo = nodo.parentElement) {
      const texto = nodo.innerText || '';
      if (texto.length > 600) break;
      if (RE.test(texto)) { tarjeta = nodo; RE.lastIndex = 0; break; }
      RE.lastIndex = 0;
    }
    if (!tarjeta) continue;
    const texto = tarjeta.innerText;
    const precios = (texto.match(RE) || []);
    const titulo = tarjeta.querySelector('h1,h2,h3,h4,[class*="title" i],[class*="name" i],[class*="nombre" i]');
    const img = tarjeta.querySelector('img');
    let nombre = (titulo && titulo.innerText.trim()) || (a.innerText || '').trim() || (img && img.alt) || '';
    nombre = nombre.split('\n').filter(l => l.trim() && !RE.test(l) && (RE.lastIndex = 0, true))[0] || '';
    RE.lastIndex = 0;
    if (nombre.length < 4 || !precios.length) continue;
    const tachado = [...tarjeta.querySelectorAll('s,del,strike,[class*="old" i],[class*="before" i],[class*="regular" i],[class*="list" i],[class*="tachado" i],[class*="strike" i]')]
        .map(n => (n.innerText.match(RE) || [])[0]).filter(Boolean)[0] || '';
    RE.lastIndex = 0;
    vistos.add(href);
    salida.push({nombre, marca: '', precios, antes: tachado, url: href, imagen: img ? (img.currentSrc || img.src) : ''});
  }
  return salida;
}"""

_estado: dict[str, Any] = {}
_candado = asyncio.Lock()


def carpeta_perfil() -> Path:
    base = Path(os.environ.get("OFERTAS_CACHE") or Path.home() / ".cache" / "ofertas")
    return base / "perfil-navegador"


def precio_en_pesos(texto: str) -> float:
    """Lee un precio en pesos, venga a la colombiana o con el formato de Amazon.

    "$ 134.000" pasa a 134000; "COP 1,322,666.93" pasa a 1322666.93. Devuelve 0 si
    el precio está en otra moneda, para no mezclar dólares con pesos.
    """
    texto = (texto or "").replace("\xa0", " ").strip()
    if re.search(r"US\$|USD|€|EUR", texto):
        return 0.0
    numero = re.sub(r"[^\d.,]", "", texto)
    if "," in numero and "." in numero and numero.rfind(".") > numero.rfind(","):
        try:
            return float(numero.replace(",", ""))
        except ValueError:
            return 0.0
    if re.fullmatch(r"\d{1,3}(,\d{3})+", numero):
        return float(numero.replace(",", ""))
    return precio_de_texto(numero)


def interpretar_producto(dato: dict, tienda: Tienda) -> Oferta | None:
    anterior = precio_en_pesos(dato.get("antes") or "")
    if "precios" in dato:
        # Extractor genérico: se toma el menor precio visible como precio de venta y el
        # mayor como precio de lista. Puede ser un precio condicionado (membresía, tarjeta).
        visibles = [v for v in map(precio_en_pesos, dato["precios"]) if v > 0]
        precio = min(visibles, default=0.0)
        anterior = max([anterior, *visibles], default=0.0)
    else:
        precio = precio_en_pesos(dato.get("precio") or "")
    nombre = re.sub(r"\s+", " ", dato.get("nombre") or "").strip()
    if precio <= 0 or not nombre or not dato.get("url"):
        return None
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=nombre,
        marca=re.sub(r"\s+", " ", dato.get("marca") or "").strip(),
        precio=precio,
        precio_lista=max(anterior, precio),
        url=dato["url"],
        imagen=dato.get("imagen") or None,
    )


async def _contexto():
    """Abre el navegador una sola vez por búsqueda y lo comparte entre tiendas."""
    async with _candado:
        if "contexto" not in _estado:
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise ErrorTienda(
                    "requiere el navegador: instala el extra con `uv sync --extra navegador`"
                ) from exc
            try:
                motor = await async_playwright().start()
                _estado["motor"] = motor
                _estado["contexto"] = await motor.chromium.launch_persistent_context(
                    str(carpeta_perfil()),
                    channel="msedge",
                    headless=os.environ.get("OFERTAS_NAVEGADOR_OCULTO") == "1",
                    locale="es-CO",
                    viewport={"width": 1280, "height": 900},
                )
            except Exception as exc:
                await cerrar()
                raise ErrorTienda(f"no se pudo abrir Edge ({type(exc).__name__})") from exc
        return _estado["contexto"]


async def cerrar() -> None:
    """Cierra el navegador si se abrió. El motor lo llama al terminar cada búsqueda."""
    contexto = _estado.pop("contexto", None)
    motor = _estado.pop("motor", None)
    try:
        if contexto is not None:
            await contexto.close()
    finally:
        if motor is not None:
            await motor.stop()


async def _leer(pagina: Any, url: str, extractor: str, intentos: int = INTENTOS):
    """Carga la URL y corre el extractor hasta que aparezcan resultados."""
    respuesta = await pagina.goto(url, wait_until="domcontentloaded", timeout=TIEMPO_CARGA_MS)
    # Los resultados se dibujan después de cargar: se consulta cada segundo hasta que
    # aparezcan, y una vez más para dar tiempo a que terminen de llegar.
    datos: list = []
    for _ in range(intentos):
        await pagina.wait_for_timeout(PAUSA_MS)
        datos = await pagina.evaluate(extractor)
        if datos:
            await pagina.wait_for_timeout(PAUSA_MS)
            datos = await pagina.evaluate(extractor)
            break
    return respuesta, datos


async def _leer_tienda_de_marca(pagina: Any, tienda: Tienda, consulta: str, extractor: str):
    """Prueba cada palabra de la consulta como nombre de una tienda oficial de marca.

    MercadoLibre exige verificación en su buscador, pero no en la portada de sus
    tiendas oficiales (`/tienda/lenovo`). Si la palabra no es una tienda, el sitio
    redirige al directorio de tiendas y se pasa a la siguiente.
    """
    respuesta, datos = None, []
    palabras = [p for p in normalizar(consulta).split() if len(p) >= 2][:MAX_MARCAS]
    for palabra in palabras:
        respuesta, datos = await _leer(
            pagina, tienda.busqueda.format(q=quote(palabra, safe="")), extractor, intentos=4
        )
        if datos and f"/tienda/{palabra}" in pagina.url:
            return respuesta, datos
        datos = []
    return respuesta, datos


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


async def buscar(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int = 50,
    incluir_agotados: bool = False,
) -> tuple[list[Oferta], int, int | None]:
    extractor = EXTRACTORES.get(tienda.id, GENERICO)
    contexto = await _contexto()
    pagina = await contexto.new_page()
    try:
        try:
            if tienda.id in POR_MARCA:
                respuesta, datos = await _leer_tienda_de_marca(pagina, tienda, consulta, extractor)
            else:
                respuesta, datos = await _leer(
                    pagina, tienda.busqueda.format(q=quote(consulta, safe="")), extractor
                )
            titulo = await pagina.title()
            texto = (await pagina.inner_text("body"))[:3000] if not datos else ""
        except Exception as exc:
            raise ErrorTienda(f"el navegador no pudo cargar la página ({type(exc).__name__})") from exc
        if not datos:
            if respuesta is not None and respuesta.status in (401, 403, 429):
                raise ErrorTienda(f"respondió HTTP {respuesta.status} incluso en el navegador")
            if _RE_RETO.search(titulo) or _RE_RETO.search(texto):
                raise ErrorTienda(
                    "la tienda pide una verificación; resuélvela a mano con "
                    f"`ofertas navegador {tienda.id}` y repite la búsqueda"
                )
        ofertas = [
            oferta
            for dato in datos[:limite]
            if (oferta := interpretar_producto(dato, tienda)) is not None
        ]
        return ofertas, len(datos), None
    finally:
        await pagina.close()


async def abrir_para_verificar(tienda: Tienda) -> None:
    """Abre la tienda en una ventana visible y espera a que la persona la cierre."""
    os.environ.pop("OFERTAS_NAVEGADOR_OCULTO", None)
    contexto = await _contexto()
    try:
        pagina = await contexto.new_page()
        await pagina.goto(tienda.url_base, wait_until="domcontentloaded", timeout=TIEMPO_CARGA_MS)
        await pagina.wait_for_event("close", timeout=0)
    finally:
        await cerrar()
