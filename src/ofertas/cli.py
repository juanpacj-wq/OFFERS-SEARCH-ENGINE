"""Interfaz de línea de comandos: `ofertas buscar "audífonos sony"`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from ofertas import motor
from ofertas.conectores import navegador
from ofertas.entorno import cargar_env
from ofertas.modelos import Resultado, agrupar_por_ean
from ofertas.tiendas import PENDIENTES, TIENDAS, seleccionar


def pesos(valor: float) -> str:
    """Formatea un precio en pesos colombianos: 1234567 pasa a $1.234.567."""
    return "$" + f"{round(valor):,}".replace(",", ".")


def _recortar(texto: str, ancho: int) -> str:
    return texto if len(texto) <= ancho else texto[: ancho - 1] + "…"


def presentar(resultado: Resultado, maximo: int) -> str:
    """Arma el texto legible de un resultado: tabla, coincidencias y cobertura."""
    lineas: list[str] = []
    ofertas = resultado.ofertas[:maximo]
    if not ofertas:
        lineas.append(f'No encontré ofertas para "{resultado.consulta}".')
    else:
        lineas.append(
            f'{len(resultado.ofertas)} ofertas para "{resultado.consulta}"'
            f" (muestro {len(ofertas)}):"
        )
        lineas.append("")
        lineas.append(f"{'Precio':>12}  {'Antes':>12}  {'Dcto':>5}  {'Tienda':<13} Producto")
        for o in ofertas:
            antes = pesos(o.precio_lista) if o.descuento_pct else ""
            dcto = f"{o.descuento_pct:.0f}%" if o.descuento_pct else ""
            nombre = _recortar(f"{o.nombre} ({o.marca})" if o.marca else o.nombre, 70)
            lineas.append(
                f"{pesos(o.precio):>12}  {antes:>12}  {dcto:>5}  {o.tienda:<13} {nombre}"
            )
            tarjeta = (
                f"  (con la tarjeta de la tienda: {pesos(o.precio_tarjeta)})"
                if o.precio_tarjeta
                else ""
            )
            lineas.append(f"{'':>12}  {o.url}{tarjeta}")

    grupos = agrupar_por_ean(resultado.ofertas)
    if grupos:
        lineas.append("")
        lineas.append("Mismo producto en varias tiendas (por código de barras):")
        for ean, grupo in grupos.items():
            lineas.append(f"  {_recortar(grupo[0].nombre, 70)} [{ean}]")
            for o in grupo:
                lineas.append(f"    {pesos(o.precio):>12}  {o.tienda}")

    lineas.append("")
    lineas.append("Cobertura:")
    for t in resultado.tiendas:
        if t.ok:
            total = f" de {t.total_en_tienda}" if t.total_en_tienda is not None else ""
            lineas.append(
                f"  {t.tienda:<13} revisados {t.encontrados}{total},"
                f" relevantes {t.relevantes} ({t.segundos} s)"
            )
        else:
            lineas.append(f"  {t.tienda:<13} FALLÓ: {t.error} ({t.segundos} s)")
    return "\n".join(lineas)


def _analizador() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="ofertas", description="Busca un producto en tiendas en línea de Colombia."
    )
    comandos = analizador.add_subparsers(dest="comando", required=True)

    buscar = comandos.add_parser("buscar", help="Busca un producto y ordena por precio.")
    buscar.add_argument("consulta", help='Lo que buscas, por ejemplo "morral totto".')
    buscar.add_argument(
        "--tiendas", help="Lista separada por comas (por defecto, todas). Ver `ofertas tiendas`."
    )
    buscar.add_argument("--max", type=int, default=20, help="Ofertas a mostrar (20).")
    buscar.add_argument(
        "--por-tienda", type=int, default=50,
        help="Productos a revisar en cada tienda (50).",
    )
    buscar.add_argument("--orden", choices=motor.ORDENES, default="precio")
    buscar.add_argument(
        "--descuento-min", type=float, default=0.0,
        help="Solo ofertas con al menos este porcentaje de descuento.",
    )
    buscar.add_argument("--precio-max", type=float, help="Solo ofertas hasta este precio.")
    buscar.add_argument(
        "--agotados", action="store_true", help="Incluye productos sin existencias."
    )
    buscar.add_argument(
        "--sin-filtro", action="store_true",
        help="No exige que el nombre contenga todas las palabras buscadas.",
    )
    buscar.add_argument("--json", action="store_true", help="Salida en JSON.")
    buscar.add_argument(
        "--navegador", action="store_true",
        help="Incluye las tiendas que abren una ventana de Edge (Amazon, Dafiti, Decathlon).",
    )

    comandos.add_parser("tiendas", help="Lista las tiendas disponibles.")
    verificar = comandos.add_parser(
        "navegador",
        help="Abre una tienda en Edge para resolver a mano una verificación.",
    )
    verificar.add_argument("tienda", help="Identificador de la tienda, por ejemplo amazon.")
    return analizador


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows no siempre usa UTF-8; sin esto fallan las tildes.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")

    cargar_env()
    args = _analizador().parse_args(argv)

    if args.comando == "tiendas":
        for t in TIENDAS:
            nota = "" if t.por_defecto else "  (solo con --navegador o al nombrarla)"
            print(f"{t.id:<15} {t.nombre:<15} {t.url_base}{nota}")
        print()
        print("Aún sin conectar:")
        for nombre, motivo in PENDIENTES:
            print(f"  {nombre:<15} {motivo}")
        return 0

    if args.comando == "navegador":
        try:
            (tienda,) = seleccionar([args.tienda])
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"Abriendo {tienda.nombre} en Edge. Cierra la pestaña cuando termines.")
        try:
            asyncio.run(navegador.abrir_para_verificar(tienda))
        except Exception as exc:
            print(f"No se pudo abrir el navegador: {exc}", file=sys.stderr)
            return 1
        return 0

    if not args.consulta.strip():
        print("La consulta no puede estar vacía.", file=sys.stderr)
        return 2
    if args.max < 1 or args.por_tienda < 1:
        print("--max y --por-tienda deben ser mayores que cero.", file=sys.stderr)
        return 2
    try:
        tiendas = seleccionar(
            [t.strip() for t in args.tiendas.split(",") if t.strip()] if args.tiendas else None,
            con_navegador=args.navegador,
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    resultado = asyncio.run(
        motor.buscar(
            args.consulta.strip(),
            tiendas,
            limite_por_tienda=args.por_tienda,
            incluir_agotados=args.agotados,
            filtrar=not args.sin_filtro,
            descuento_minimo=args.descuento_min,
            precio_maximo=args.precio_max,
            orden=args.orden,
        )
    )
    if args.json:
        datos = resultado.a_dict()
        datos["total_ofertas"] = len(datos["ofertas"])
        datos["ofertas"] = datos["ofertas"][: args.max]
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    else:
        print(presentar(resultado, args.max))
    # Código 1 si ninguna tienda respondió: no hay resultado en el que confiar.
    return 0 if resultado.tiendas_consultadas else 1


if __name__ == "__main__":
    sys.exit(main())
