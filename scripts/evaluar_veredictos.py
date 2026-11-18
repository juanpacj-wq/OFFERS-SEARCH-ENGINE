"""Corre el veredicto sobre varias categorías y resume qué tanto logra comprobar.

Uso:  uv run python scripts/evaluar_veredictos.py [salida.md]

Consulta las tiendas reales y las fuentes internacionales, así que el resultado cambia
con el día. Usa una base temporal: no toca el historial ni aprovecha lo ya consultado.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from ofertas import historial, motor, veredicto, verificacion
from ofertas.tiendas import seleccionar

CONSULTAS = [
    "televisor samsung 55",
    "computador portatil lenovo",
    "celular samsung galaxy",
    "taladro percutor dewalt",
    "tenis adidas",
    "nevera no frost",
    "lavadora samsung",
    "audifonos sony",
    "morral totto",
    "colchon doble",
    "silla oficina",
    "bicicleta",
    "camiseta polo hombre",
    "consola nintendo switch",
    "perfume hombre",
]
MOSTRADAS = 20
COLUMNAS = ("descuento_real", "oferta_falsa", "sobreprecio", "sin_referencia")


async def evaluar(consulta: str, conexion) -> dict:
    inicio = time.perf_counter()
    resultado = await motor.buscar(consulta, seleccionar(None))
    await verificacion.verificar(resultado, conexion, mostradas=MOSTRADAS)
    segundos = time.perf_counter() - inicio
    mostradas = resultado.ofertas[:MOSTRADAS]
    con_descuento = [
        o for o in mostradas if o.descuento_pct >= veredicto.DESCUENTO_ANUNCIADO_MINIMO
    ]
    conteo = {c: 0 for c in COLUMNAS}
    for oferta in con_descuento:
        conteo[oferta.veredicto["clase"]] = conteo.get(oferta.veredicto["clase"], 0) + 1
    comprobadas = len(con_descuento) - conteo["sin_referencia"]
    todas = [
        o for o in resultado.ofertas
        if o.descuento_pct >= veredicto.DESCUENTO_ANUNCIADO_MINIMO
    ]
    todas_comprobadas = [o for o in todas if o.veredicto["clase"] != "sin_referencia"]
    return {
        "consulta": consulta,
        "ofertas": len(resultado.ofertas),
        "con_descuento": len(con_descuento),
        "conteo": conteo,
        "comprobadas": comprobadas,
        "todas": len(todas),
        "todas_comprobadas": len(todas_comprobadas),
        "todas_reales": sum(
            1 for o in todas_comprobadas if o.veredicto["clase"] == "descuento_real"
        ),
        "aproximadas": sum(
            1 for o in con_descuento if o.veredicto.get("confianza") == "aproximada"
        ),
        "con_internacional": sum(1 for o in mostradas if "internacional" in o.veredicto),
        "tiendas_ok": len(resultado.tiendas_consultadas),
        "tiendas_fallidas": len(resultado.tiendas_fallidas),
        "segundos": segundos,
    }


async def main() -> None:
    filas = []
    with tempfile.TemporaryDirectory() as carpeta, historial.abrir(Path(carpeta) / "e.db") as con:
        for consulta in CONSULTAS:
            fila = await evaluar(consulta, con)
            filas.append(fila)
            print(f"{consulta}: {fila['comprobadas']} de {fila['con_descuento']} comprobadas"
                  f" en {fila['segundos']:.0f} s", file=sys.stderr)

    lineas = [
        "# Evaluación del veredicto por categoría",
        "",
        f"Corrida del {date.today().isoformat()} con `scripts/evaluar_veredictos.py`, contra las"
        " tiendas reales y sin historial previo. Se miran las primeras"
        f" {MOSTRADAS} ofertas de cada búsqueda (ordenadas por precio) y, de ellas, las que"
        " anuncian descuento.",
        "",
        "| Búsqueda | Ofertas | Con descuento | Reales | Engañosas | Más caras | Sin verificar"
        " | Comprobadas | Aproximadas | Con precio internacional | Toda la búsqueda | Tiempo |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for f in filas:
        c = f["conteo"]
        pct = f"{f['comprobadas'] / f['con_descuento'] * 100:.0f}%" if f["con_descuento"] else "n/a"
        lineas.append(
            f"| {f['consulta']} | {f['ofertas']} | {f['con_descuento']} | {c['descuento_real']}"
            f" | {c['oferta_falsa']} | {c['sobreprecio']} | {c['sin_referencia']} | {pct}"
            f" | {f['aproximadas']} | {f['con_internacional']} de {MOSTRADAS}"
            f" | {f['todas_comprobadas']} de {f['todas']}"
            + (f" ({f['todas_comprobadas'] / f['todas'] * 100:.0f}%)" if f["todas"] else "")
            + f", {f['todas_reales']} reales | {f['segundos']:.0f} s |"
        )
    total = sum(f["con_descuento"] for f in filas)
    comprobadas = sum(f["comprobadas"] for f in filas)
    reales = sum(f["conteo"]["descuento_real"] for f in filas)
    lineas += [
        "",
        f"**Total:** {total} ofertas con descuento anunciado; {comprobadas}"
        f" ({comprobadas / total * 100:.0f}%) se pudieron comprobar y, de esas, {reales}"
        f" ({reales / comprobadas * 100:.0f}%) eran descuentos reales. En todas las ofertas"
        f" de las búsquedas: {sum(f['todas_comprobadas'] for f in filas)} comprobadas de"
        f" {sum(f['todas'] for f in filas)}, y {sum(f['todas_reales'] for f in filas)} reales."
        if total and comprobadas else "**Total:** sin ofertas con descuento.",
        "",
        "- **Comprobadas:** tienen veredicto distinto de \"sin verificar\".",
        "- **Aproximadas:** su veredicto se apoya en un producto equivalente o en equipos de"
        " igual ficha técnica; están incluidas en las comprobadas.",
        "- **Con precio internacional:** ofertas mostradas para las que se halló referencia"
        " afuera, tengan o no descuento anunciado.",
        "- **Toda la búsqueda:** las mismas cuentas sobre todas las ofertas con descuento"
        " anunciado, no solo las 20 primeras. Ahí no se investiga el precio internacional"
        " (solo se hace para lo que se muestra), así que es el alcance del mercado local.",
        "- **Tiempo:** búsqueda en las tiendas más verificación, sin nada en caché.",
    ]
    texto = "\n".join(lineas) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(texto, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    asyncio.run(main())
