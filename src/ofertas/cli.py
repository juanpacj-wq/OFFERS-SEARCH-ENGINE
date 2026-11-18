"""Interfaz de línea de comandos: `ofertas buscar "audífonos sony"`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from ofertas import historial, identidad, motor, veredicto, verificacion
from ofertas.conectores import navegador
from ofertas.entorno import cargar_env
from ofertas.modelos import Oferta, Resultado, Tienda, agrupar_por_ean
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
            if o.veredicto:
                lineas.append(f"{'':>12}  >> {o.veredicto['titulo']}: {o.veredicto['texto']}")
            if o.historial:
                veces = o.historial["veces_visto"]
                lineas.append(
                    f"{'':>12}  Historial (visto {veces} {'vez' if veces == 1 else 'veces'}"
                    f" desde {o.historial['primera_vez']}): {o.historial['lectura']}"
                )

    grupos = agrupar_por_ean(resultado.ofertas)
    if grupos:
        lineas.append("")
        lineas.append("Mismo producto en varias tiendas (por código de barras):")
        for ean, grupo in grupos.items():
            lineas.append(f"  {_recortar(grupo[0].nombre, 70)} [{ean}]")
            for o in grupo:
                lineas.append(f"    {pesos(o.precio):>12}  {o.tienda}")

    conteo = verificacion.resumen(resultado.ofertas)
    if conteo:
        lineas.append("")
        lineas.append(
            "De las ofertas con descuento anunciado: "
            + ", ".join(
                f"{n} {veredicto.nombre_de(clase, n)}"
                for clase, n in sorted(conteo.items(), key=lambda par: -par[1])
            )
            + "."
        )
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
    buscar.add_argument(
        "--orden", choices=(*motor.ORDENES, "ahorro"), default="precio",
        help="precio, descuento (el anunciado) o ahorro (el real, frente al precio real).",
    )
    buscar.add_argument(
        "--solo-reales", action="store_true",
        help="Solo ofertas cuyo precio está de verdad por debajo del precio real.",
    )
    buscar.add_argument(
        "--sin-internacional", action="store_true",
        help="No investiga el precio internacional (el juicio usa solo tiendas e historial).",
    )
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
    buscar.add_argument(
        "--sin-historial", action="store_true",
        help="No consulta ni guarda el historial de precios en esta búsqueda.",
    )

    comandos.add_parser("tiendas", help="Lista las tiendas disponibles.")
    verificar = comandos.add_parser(
        "navegador",
        help="Abre una tienda en Edge para resolver a mano una verificación.",
    )
    verificar.add_argument("tienda", help="Identificador de la tienda, por ejemplo amazon.")

    profundo = comandos.add_parser(
        "verificar",
        help="Investiga a fondo si las ofertas de un producto son descuentos reales.",
    )
    profundo.add_argument("consulta", help='El producto, por ejemplo "galaxy s25 ultra 256gb".')
    profundo.add_argument("--tiendas", help="Tiendas a revisar, separadas por comas.")
    profundo.add_argument("--max", type=int, default=8, help="Productos a mostrar (8).")
    profundo.add_argument("--json", action="store_true", help="Salida en JSON.")
    profundo.add_argument(
        "--navegador", action="store_true",
        help="Además consulta Amazon abriendo Edge, como fuente de precio internacional.",
    )

    ver = comandos.add_parser(
        "historial", help="Muestra los precios guardados de los productos que coincidan."
    )
    ver.add_argument("texto", help='Palabras del nombre, por ejemplo "arroz diana".')
    ver.add_argument("--max", type=int, default=10, help="Productos a mostrar (10).")
    ver.add_argument("--json", action="store_true", help="Salida en JSON.")

    seguir = comandos.add_parser("seguir", help="Agrega una búsqueda a la lista de seguimiento.")
    seguir.add_argument("consulta", help="La búsqueda que quieres seguir.")
    seguir.add_argument("--objetivo", type=float, help="Precio al que te interesa comprar.")
    seguir.add_argument("--tiendas", help="Tiendas a revisar, separadas por comas.")

    lista = comandos.add_parser("seguimientos", help="Muestra la lista de seguimiento.")
    lista.add_argument("--json", action="store_true", help="Salida en JSON.")
    dejar = comandos.add_parser("dejar", help="Quita una búsqueda de la lista de seguimiento.")
    dejar.add_argument("id", type=int, help="Número que muestra `ofertas seguimientos`.")
    revisar = comandos.add_parser(
        "revisar", help="Busca ahora todo lo que sigues y dice qué llegó a su precio objetivo."
    )
    revisar.add_argument("--json", action="store_true", help="Salida en JSON.")
    return analizador


def _lista_de_tiendas(texto: str | None) -> list[str] | None:
    return [t.strip() for t in texto.split(",") if t.strip()] if texto else None


def _buscar_con_historial(
    consulta: str,
    tiendas: list[Tienda],
    usar_historial: bool = True,
    verificar: dict | None = None,
    **opciones,
) -> Resultado:
    """Busca, anota el historial, emite el veredicto de cada oferta y guarda lo observado.

    `verificar` son las opciones de `verificacion.verificar`; con None no se verifica.
    Sin historial, la base se abre en memoria: el veredicto sigue funcionando, pero no
    recuerda nada ni aprovecha lo ya consultado afuera.
    """
    resultado = asyncio.run(motor.buscar(consulta, tiendas, **opciones))
    resultado.avisos = []
    try:
        ruta = None if usar_historial else historial.EN_MEMORIA
        with historial.abrir(ruta) as conexion:
            if usar_historial:
                historial.anotar(conexion, resultado)
            if verificar is not None:
                resultado.grupos, resultado.avisos = asyncio.run(
                    verificacion.verificar(resultado, conexion, **verificar)
                )
            if usar_historial:
                historial.registrar(conexion, resultado)
    except Exception as exc:
        # Historial y veredicto son complementos: si fallan, la búsqueda sigue siendo válida.
        print(f"Aviso: no se pudo completar la verificación ({exc}).", file=sys.stderr)
    return resultado


def _ordenar_por_ahorro(resultado: Resultado) -> None:
    def clave(oferta: Oferta) -> tuple:
        ahorro = (oferta.veredicto or {}).get("ahorro_real_pct")
        return (ahorro is None, -(ahorro or 0), oferta.precio)

    resultado.ofertas.sort(key=clave)


def _solo_reales(resultado: Resultado) -> None:
    resultado.ofertas = [
        o for o in resultado.ofertas
        if o.veredicto
        and o.veredicto["clase"] in veredicto.FAVORABLES
        and o.veredicto["confianza"] != "aproximada"
    ]


def _verificar_a_fondo(args: argparse.Namespace) -> int:
    """Comando `verificar`: un informe por producto con toda la evidencia."""
    try:
        tiendas = seleccionar(_lista_de_tiendas(args.tiendas))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    resultado = _buscar_con_historial(
        args.consulta.strip(), tiendas,
        verificar={"profundo": True, "con_amazon": args.navegador, "max_grupos": args.max},
    )
    grupos = verificacion.ordenar_para_informe(
        getattr(resultado, "grupos", None) or identidad.agrupar(resultado.ofertas)
    )[: args.max]
    if args.json:
        datos = {
            "consulta": resultado.consulta,
            "productos": [
                {"nombre": g.principal.nombre, "coincidencia": g.via,
                 "ofertas": [o.a_dict() for o in sorted(g.ofertas, key=lambda o: o.precio)]}
                for g in grupos
            ],
            "avisos": resultado.avisos,
            "tiendas_fallidas": [asdict(t) for t in resultado.tiendas_fallidas],
        }
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return 0
    if not grupos:
        print(f'No encontré ofertas para "{resultado.consulta}".')
    for grupo in grupos:
        print(_recortar(grupo.principal.nombre, 100))
        primero = grupo.ofertas[0].veredicto or {}
        afuera = primero.get("internacional")
        if afuera:
            clase = {"exacto": "mismo producto", "modelo": "mismo modelo",
                     "equivalente": "producto equivalente"}[afuera["coincidencia"]]
            print(
                f"  Precio internacional ({clase}): US$ {afuera['precio_usd']:,.2f},"
                f" {pesos(afuera['con_iva'])} con IVA, normal hasta {pesos(afuera['tope_normal'])}"
            )
            print(f"    {_recortar(afuera['ejemplo'], 90)}  [{', '.join(afuera['fuentes'])}]")
        else:
            print("  Precio internacional: no se halló una referencia confiable.")
        for o in sorted(grupo.ofertas, key=lambda o: o.precio):
            antes = (
                f" (antes {pesos(o.precio_lista)}, -{o.descuento_pct:.0f}%)"
                if o.descuento_pct
                else ""
            )
            print(f"  {pesos(o.precio):>12}  {o.tienda}{antes}")
            if o.veredicto:
                print(f"      >> {o.veredicto['titulo']}: {o.veredicto['texto']}")
            print(f"      {o.url}")
        print()
    for aviso in resultado.avisos:
        print(f"Aviso: {aviso}")
    if resultado.tiendas_fallidas:
        print("No respondieron: " + ", ".join(t.tienda for t in resultado.tiendas_fallidas))
    return 0


def _mostrar_historial(args: argparse.Namespace) -> int:
    with historial.abrir() as conexion:
        productos = historial.buscar_productos(conexion, args.texto, args.max)
    if args.json:
        print(json.dumps(productos, ensure_ascii=False, indent=2))
        return 0
    if not productos:
        print(f'No hay precios guardados para "{args.texto}".')
        return 0
    for p in productos:
        print(f"{p['tienda']}: {_recortar(p['nombre'], 80)}")
        print(f"  {p['url']}")
        print(
            f"  Visto {p['veces']} {'vez' if p['veces'] == 1 else 'veces'} entre"
            f" {historial.fecha_local(p['primera'])} y {historial.fecha_local(p['ultima'])};"
            f" mínimo {pesos(p['minimo'])}, máximo {pesos(p['maximo'])}"
        )
        for o in p["observaciones"][-8:]:
            rebajado = o["precio_lista"] > o["precio"]
            lista = f"  (lista {pesos(o['precio_lista'])})" if rebajado else ""
            cuando = historial.fecha_local(o["fecha"], con_hora=True)
            print(f"    {cuando}  {pesos(o['precio']):>12}{lista}")
    return 0


def _estado_de(seguimiento: historial.Seguimiento, mejor: Oferta | None) -> dict:
    """Compara el mejor precio de ahora con el objetivo y con la revisión anterior."""
    estado = {
        "id": seguimiento.id,
        "consulta": seguimiento.consulta,
        "precio_objetivo": seguimiento.precio_objetivo,
        "precio_anterior": seguimiento.ultimo_precio,
        "mejor": mejor.a_dict() if mejor else None,
        "llego_al_objetivo": bool(
            mejor
            and seguimiento.precio_objetivo is not None
            and mejor.precio <= seguimiento.precio_objetivo
        ),
        "cambio_pct": None,
    }
    if mejor and seguimiento.ultimo_precio:
        estado["cambio_pct"] = round(
            (mejor.precio - seguimiento.ultimo_precio) / seguimiento.ultimo_precio * 100, 1
        )
    return estado


def _revisar(args: argparse.Namespace) -> int:
    with historial.abrir() as conexion:
        pendientes = historial.seguimientos(conexion)
    if not pendientes:
        print('No sigues ninguna búsqueda. Agrega una con `ofertas seguir "..."`.')
        return 0
    estados = []
    for seguimiento in pendientes:
        try:
            tiendas = seleccionar(seguimiento.tiendas or None)
        except ValueError as exc:
            print(f"Seguimiento {seguimiento.id}: {exc}", file=sys.stderr)
            continue
        resultado = _buscar_con_historial(seguimiento.consulta, tiendas)
        mejor = resultado.ofertas[0] if resultado.ofertas else None
        estado = _estado_de(seguimiento, mejor)
        estado["tiendas_fallidas"] = [t.tienda for t in resultado.tiendas_fallidas]
        estados.append(estado)
        with historial.abrir() as conexion:
            historial.anotar_revision(conexion, seguimiento, mejor)
    if args.json:
        print(json.dumps(estados, ensure_ascii=False, indent=2))
        return 0
    for e in estados:
        objetivo = f" (objetivo {pesos(e['precio_objetivo'])})" if e["precio_objetivo"] else ""
        print(f"[{e['id']}] {e['consulta']}{objetivo}")
        if not e["mejor"]:
            print("    Sin ofertas en esta revisión.")
        else:
            m = e["mejor"]
            marca = "  ¡LLEGÓ AL OBJETIVO!" if e["llego_al_objetivo"] else ""
            print(f"    {pesos(m['precio'])} en {m['tienda']}: {_recortar(m['nombre'], 60)}{marca}")
            print(f"    {m['url']}")
            if e["cambio_pct"]:
                verbo = "bajó" if e["cambio_pct"] < 0 else "subió"
                print(
                    f"    {verbo} {abs(e['cambio_pct'])}% frente a"
                    f" {pesos(e['precio_anterior'])} de la revisión anterior"
                )
        if e["tiendas_fallidas"]:
            print(f"    No respondieron: {', '.join(e['tiendas_fallidas'])}")
    return 0


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

    if args.comando == "historial":
        return _mostrar_historial(args)

    if args.comando == "verificar":
        if not args.consulta.strip():
            print("La consulta no puede estar vacía.", file=sys.stderr)
            return 2
        return _verificar_a_fondo(args)

    if args.comando == "seguimientos":
        with historial.abrir() as conexion:
            lista = historial.seguimientos(conexion)
        if args.json:
            print(json.dumps([asdict(s) for s in lista], ensure_ascii=False, indent=2))
        elif not lista:
            print('No sigues ninguna búsqueda. Agrega una con `ofertas seguir "..."`.')
        for s in [] if args.json else lista:
            objetivo = f", objetivo {pesos(s.precio_objetivo)}" if s.precio_objetivo else ""
            donde = f", en {', '.join(s.tiendas)}" if s.tiendas else ""
            ultimo = (
                f"; última revisión {historial.fecha_local(s.ultima_revision)}:"
                f" {pesos(s.ultimo_precio)}"
                f" en {s.ultima_tienda}"
                if s.ultimo_precio
                else "; sin revisar todavía"
            )
            print(f"[{s.id}] {s.consulta}{objetivo}{donde}{ultimo}")
        return 0

    if args.comando == "dejar":
        with historial.abrir() as conexion:
            quitado = historial.dejar_de_seguir(conexion, args.id)
        print("Listo, ya no la sigues." if quitado else f"No hay un seguimiento número {args.id}.")
        return 0 if quitado else 2

    if args.comando == "revisar":
        return _revisar(args)

    if not args.consulta.strip():
        print("La consulta no puede estar vacía.", file=sys.stderr)
        return 2

    if args.comando == "seguir":
        if args.objetivo is not None and args.objetivo <= 0:
            print("--objetivo debe ser mayor que cero.", file=sys.stderr)
            return 2
        nombres = _lista_de_tiendas(args.tiendas)
        try:
            seleccionar(nombres)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        with historial.abrir() as conexion:
            nuevo = historial.seguir(conexion, args.consulta, nombres, args.objetivo)
        print(
            f'Listo: sigo "{nuevo.consulta}" con el número {nuevo.id}.'
            " Revísala con `ofertas revisar`."
        )
        return 0

    if args.max < 1 or args.por_tienda < 1:
        print("--max y --por-tienda deben ser mayores que cero.", file=sys.stderr)
        return 2
    try:
        tiendas = seleccionar(_lista_de_tiendas(args.tiendas), con_navegador=args.navegador)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    resultado = _buscar_con_historial(
        args.consulta.strip(),
        tiendas,
        usar_historial=not args.sin_historial,
        verificar={"mostradas": args.max, "con_internacional": not args.sin_internacional},
        limite_por_tienda=args.por_tienda,
        incluir_agotados=args.agotados,
        filtrar=not args.sin_filtro,
        descuento_minimo=args.descuento_min,
        precio_maximo=args.precio_max,
        orden="precio" if args.orden == "ahorro" else args.orden,
    )
    if args.solo_reales:
        _solo_reales(resultado)
    if args.orden == "ahorro":
        _ordenar_por_ahorro(resultado)
    if args.json:
        datos = resultado.a_dict()
        datos["avisos"] = resultado.avisos
        datos["total_ofertas"] = len(datos["ofertas"])
        datos["ofertas"] = datos["ofertas"][: args.max]
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    else:
        print(presentar(resultado, args.max))
        for aviso in resultado.avisos:
            print(f"Aviso: {aviso}")
    # Código 1 si ninguna tienda respondió: no hay resultado en el que confiar.
    return 0 if resultado.tiendas_consultadas else 1


if __name__ == "__main__":
    sys.exit(main())
