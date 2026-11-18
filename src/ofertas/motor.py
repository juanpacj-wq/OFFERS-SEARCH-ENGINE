"""Orquesta la búsqueda: consulta las tiendas en paralelo, filtra y ordena."""

from __future__ import annotations

import asyncio
import ssl
import time
import unicodedata

import httpx
import truststore

from ofertas import identidad
from ofertas.conectores import (
    alkosto,
    falabella,
    hp,
    ikea,
    lenovo,
    mercadolibre,
    navegador,
    rappi,
    samsung,
    vtex,
    woocommerce,
)
from ofertas.conectores.base import ErrorTienda
from ofertas.modelos import EstadoTienda, Oferta, Resultado, Tienda

AGENTE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
# Las páginas más pesadas (2 MB) llegan en unos 5 s; más de 12 s es una tienda caída.
TIEMPO_LIMITE = httpx.Timeout(12.0, connect=4.0)
# Tope por tienda sumando todas sus peticiones (las de navegador tienen el suyo). Una
# tienda más lenta que esto queda reportada como fallida en vez de frenar la búsqueda.
TOPE_POR_TIENDA = 15.0
ORDENES = ("precio", "descuento")
CONECTORES = {
    "vtex": vtex.buscar,
    "falabella": falabella.buscar,
    "alkosto": alkosto.buscar,
    "lenovo": lenovo.buscar,
    "hp": hp.buscar,
    "rappi": rappi.buscar,
    "samsung": samsung.buscar,
    "mercadolibre": mercadolibre.buscar,
    "woocommerce": woocommerce.buscar,
    "ikea": ikea.buscar,
    "navegador": navegador.buscar,
}


def crear_cliente(transporte: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """Cliente HTTP del motor.

    Valida los certificados contra el almacén del sistema operativo, igual que un
    navegador: con la lista que trae Python, varias tiendas fallan en redes que
    inspeccionan el tráfico o cuando el servidor omite un certificado intermedio.
    """
    return httpx.AsyncClient(
        headers={"User-Agent": AGENTE, "Accept": "application/json"},
        timeout=TIEMPO_LIMITE,
        follow_redirects=True,
        transport=transporte,
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar textos sin importar cómo se escribieron."""
    sin_tildes = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


def es_relevante(oferta: Oferta, consulta: str) -> bool:
    """Verdadero si todas las palabras de la consulta están en nombre, marca o categoría.

    También descarta los accesorios de lo buscado ("broca para taladro" al buscar un
    taladro), que de otro modo copan los primeros puestos por ser lo más barato.

    Los buscadores de las tiendas devuelven productos apenas relacionados; sin este
    filtro, ordenar por precio pondría de primeras accesorios baratos.
    """
    if identidad.es_accesorio_de(oferta.nombre, consulta):
        return False
    texto = normalizar(f"{oferta.nombre} {oferta.marca} {oferta.categoria}")
    for palabra in normalizar(consulta).split():
        if len(palabra) < 2:
            continue
        singular = palabra[:-1] if palabra.endswith("s") and len(palabra) > 3 else palabra
        if palabra not in texto and singular not in texto:
            return False
    return True


async def _buscar_en_tienda(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int,
    incluir_agotados: bool,
    filtrar: bool,
) -> tuple[list[Oferta], EstadoTienda]:
    inicio = time.perf_counter()
    try:
        conector = CONECTORES[tienda.plataforma](
            cliente, tienda, consulta, limite, incluir_agotados
        )
        if tienda.plataforma == "navegador":
            ofertas, recibidos, total = await conector
        else:
            ofertas, recibidos, total = await asyncio.wait_for(conector, TOPE_POR_TIENDA)
    except TimeoutError:
        estado = EstadoTienda(
            tienda.id, tienda.nombre, ok=False, error="tardó demasiado en responder",
            segundos=round(time.perf_counter() - inicio, 1),
        )
        return [], estado
    except Exception as exc:
        # Una tienda que cambia su formato no debe tumbar la búsqueda en las demás.
        motivo = (
            str(exc)
            if isinstance(exc, ErrorTienda)
            else f"respuesta con formato inesperado ({type(exc).__name__})"
        )
        estado = EstadoTienda(
            tienda.id, tienda.nombre, ok=False, error=motivo,
            segundos=round(time.perf_counter() - inicio, 1),
        )
        return [], estado
    # Las tiendas repiten productos (un patrocinado y su resultado normal, por ejemplo).
    ofertas = list({(o.url, o.precio): o for o in ofertas}.values())
    if filtrar:
        ofertas = [o for o in ofertas if es_relevante(o, consulta)]
    estado = EstadoTienda(
        tienda.id, tienda.nombre, ok=True, encontrados=recibidos,
        relevantes=len(ofertas), total_en_tienda=total,
        segundos=round(time.perf_counter() - inicio, 1),
    )
    return ofertas, estado


def ordenar(ofertas: list[Oferta], orden: str) -> list[Oferta]:
    if orden == "descuento":
        return sorted(ofertas, key=lambda o: (-o.descuento_pct, o.precio))
    return sorted(ofertas, key=lambda o: o.precio)


async def buscar(
    consulta: str,
    tiendas: list[Tienda],
    *,
    limite_por_tienda: int = 50,
    incluir_agotados: bool = False,
    filtrar: bool = True,
    descuento_minimo: float = 0.0,
    precio_maximo: float | None = None,
    orden: str = "precio",
    transporte: httpx.AsyncBaseTransport | None = None,
) -> Resultado:
    """Busca `consulta` en todas las `tiendas` y devuelve ofertas con su cobertura.

    Una tienda que falla no tumba la búsqueda: queda registrada en el resultado
    como fallida, con el motivo.
    """
    try:
        async with crear_cliente(transporte) as cliente:
            respuestas = await asyncio.gather(
                *(
                    _buscar_en_tienda(
                        cliente, t, consulta, limite_por_tienda, incluir_agotados, filtrar
                    )
                    for t in tiendas
                )
            )
    finally:
        await navegador.cerrar()
    ofertas = [o for lista, _ in respuestas for o in lista]
    if descuento_minimo > 0:
        ofertas = [o for o in ofertas if o.descuento_pct >= descuento_minimo]
    if precio_maximo is not None:
        ofertas = [o for o in ofertas if o.precio <= precio_maximo]
    return Resultado(
        consulta=consulta,
        ofertas=ordenar(ofertas, orden),
        tiendas=[estado for _, estado in respuestas],
    )
