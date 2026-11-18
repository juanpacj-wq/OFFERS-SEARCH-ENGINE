"""Flujo completo por el comando: buscar, agrupar, investigar afuera y emitir veredicto."""

import json

import httpx
import pytest

from ofertas.cli import main

TV = "Televisor Samsung 55 Pulgadas Smarttv 4K UN55CU7000KXZL"


def producto_vtex(nombre, precio, lista, ean="", vendedor="Tienda", marca="SAMSUNG"):
    return {
        "productName": nombre, "brand": marca, "linkText": nombre.lower().replace(" ", "-"),
        "items": [{"ean": ean, "sellers": [{"sellerName": vendedor, "commertialOffer": {
            "Price": precio, "ListPrice": lista, "AvailableQuantity": 3}}]}],
    }


# Tres tiendas venden el mismo televisor a casi el mismo precio; solo Olímpica infla la
# lista para anunciar 50%. Jumbo tiene otro televisor que nadie más vende.
CATALOGOS = {
    "www.olimpica.com": [producto_vtex(TV, 1589900, 3209900, "8806090000001", "Olimpica")],
    "www.exito.com": [producto_vtex(TV, 1599900, 1599900, "8806090000001", "Exito")],
    "www.pepeganga.com": [producto_vtex(TV, 1610000, 1610000, "8806090000001", "Pepe Ganga")],
    "www.jumbocolombia.com": [
        producto_vtex("Televisor Samsung 55 Pulgadas QLED QN55Q7FAAKXZL", 2500000, 4000000,
                      "8806090000002", "Jumbo"),
    ],
}
TIENDAS = "olimpica,exito,pepeganga,jumbo"


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    """Simula las tiendas, la TRM y la tienda de Samsung en EE. UU."""
    monkeypatch.setenv("OFERTAS_DATOS", str(tmp_path))
    visitas = []

    def manejador(peticion):
        host = peticion.url.host
        visitas.append(host)
        if host in CATALOGOS:
            return httpx.Response(200, json=CATALOGOS[host])
        if host == "www.datos.gov.co":
            return httpx.Response(200, json=[{"valor": "4000"}])
        if host == "api.shop.samsung.com":
            if peticion.url.params["query"] == "UN55CU7000":
                return httpx.Response(200, json={"products": [
                    {"code": "UN55CU7000FXZA", "name": '55" Class Crystal UHD CU7000',
                     "price": {"value": 380.0}},
                ]})
            return httpx.Response(200, json={"products": []})
        return httpx.Response(404, json={})

    real = httpx.AsyncClient

    def cliente_simulado(**opciones):
        opciones.pop("verify", None)
        opciones["transport"] = httpx.MockTransport(manejador)
        return real(**opciones)

    monkeypatch.setattr(httpx, "AsyncClient", cliente_simulado)
    return visitas


def buscar_json(*argumentos):
    return ["buscar", "televisor samsung 55", "--tiendas", TIENDAS, "--json", *argumentos]


def test_detecta_el_precio_normal_presentado_como_oferta(mundo, capsys):
    assert main(buscar_json()) == 0
    datos = json.loads(capsys.readouterr().out)
    por_tienda = {o["tienda_id"]: o for o in datos["ofertas"]}

    inflada = por_tienda["olimpica"]["veredicto"]
    assert inflada["clase"] == "oferta_falsa"
    assert inflada["confianza"] == "fuerte"
    assert inflada["precio_real"] == 1604950  # mediana de Éxito y Pepe Ganga
    assert inflada["descuento_anunciado_pct"] == 50.5
    assert inflada["lista_inflada_pct"] == 100.0
    assert inflada["coincidencia_entre_tiendas"] == "ean"
    assert inflada["evidencias"][0]["tipo"] == "mercado"

    assert por_tienda["exito"]["veredicto"]["clase"] == "precio_normal"

    # El precio internacional sale del mismo modelo con el sufijo de EE. UU.
    afuera = inflada["internacional"]
    assert (afuera["coincidencia"], afuera["precio_usd"]) == ("modelo", 380.0)
    assert afuera["trm"] == 4000.0
    assert afuera["con_iva"] == 1808800
    assert afuera["fuentes"] == ["Samsung EE. UU."]

    # El televisor que solo tiene Jumbo no se puede comprobar, y se dice.
    solitario = por_tienda["jumbo"]["veredicto"]
    assert solitario["clase"] == "sin_referencia"
    assert "no hay con qué comprobarlo" in solitario["texto"]


def test_la_salida_de_texto_muestra_el_veredicto_y_el_conteo(mundo, capsys):
    assert main(["buscar", "televisor samsung 55", "--tiendas", TIENDAS]) == 0
    salida = capsys.readouterr().out
    assert ">> Oferta engañosa: Precio real: cerca de $1.604.950" in salida
    assert "(mediana de 2 tiendas más)" in salida
    assert "El precio de lista está inflado 100% sobre el real" in salida
    assert "con descuento anunciado: 1 oferta engañosa, 1 sin verificar." in salida


def test_solo_reales_descarta_enganosas_y_sin_verificar(mundo, capsys):
    assert main(buscar_json("--solo-reales")) == 0
    assert json.loads(capsys.readouterr().out)["ofertas"] == []


def test_orden_por_ahorro_real(mundo, capsys):
    assert main(buscar_json("--orden", "ahorro")) == 0
    ofertas = json.loads(capsys.readouterr().out)["ofertas"]
    ahorros = [o["veredicto"]["ahorro_real_pct"] for o in ofertas]
    assert ahorros[-1] is None  # lo que no se pudo verificar va al final
    conocidos = [a for a in ahorros if a is not None]
    assert conocidos == sorted(conocidos, reverse=True)


def test_sin_internacional_juzga_solo_con_el_mercado_local(mundo, capsys):
    assert main(buscar_json("--sin-internacional")) == 0
    datos = json.loads(capsys.readouterr().out)
    olimpica = next(o for o in datos["ofertas"] if o["tienda_id"] == "olimpica")
    assert olimpica["veredicto"]["clase"] == "oferta_falsa"
    assert "internacional" not in olimpica["veredicto"]
    assert "api.shop.samsung.com" not in mundo and "www.datos.gov.co" not in mundo


def test_sin_historial_tambien_verifica_y_no_guarda(mundo, capsys, tmp_path):
    assert main(buscar_json("--sin-historial")) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["ofertas"][0]["veredicto"]["clase"] in ("oferta_falsa", "precio_normal")
    assert not (tmp_path / "historial.db").exists()


def test_la_segunda_busqueda_no_repite_la_consulta_internacional(mundo, capsys):
    assert main(buscar_json()) == 0
    primera = mundo.count("api.shop.samsung.com")
    assert primera > 0
    assert main(buscar_json()) == 0
    assert mundo.count("api.shop.samsung.com") == primera
    capsys.readouterr()


def test_comando_verificar_informa_por_producto(mundo, capsys):
    assert main(["verificar", "televisor samsung 55", "--tiendas", TIENDAS]) == 0
    salida = capsys.readouterr().out
    assert "Precio internacional (mismo modelo): US$ 380.00, $1.808.800 con IVA" in salida
    assert "Olímpica (antes $3.209.900, -50%)" in salida
    assert ">> Oferta engañosa" in salida
    assert "Precio internacional: no se halló una referencia confiable." in salida

    assert main(["verificar", "televisor samsung 55", "--tiendas", TIENDAS, "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert len(datos["productos"]) == 2
    assert len(datos["productos"][0]["ofertas"]) == 3  # primero el que tienen más tiendas
    assert main(["verificar", "  "]) == 2


def test_lo_no_comprobable_trae_la_proporcion_de_reales_de_la_busqueda():
    from ofertas import verificacion
    from ofertas.modelos import Oferta

    def con_veredicto(clase, confianza="fuerte", lista=200.0):
        oferta = Oferta("t", "T", "Producto", "M", 100.0, lista, "https://t/p")
        oferta.veredicto = {"clase": clase, "confianza": confianza, "texto": "Base."}
        return oferta

    comprobadas = [con_veredicto("oferta_falsa") for _ in range(4)]
    comprobadas += [con_veredicto("descuento_real"), con_veredicto("sobreprecio")]
    aproximada = con_veredicto("descuento_real", "aproximada")  # no cuenta: no es firme
    sin_descuento = con_veredicto("buen_precio", lista=100.0)  # no anuncia descuento
    dudosa = con_veredicto("sin_referencia", "")
    todas = [*comprobadas, aproximada, sin_descuento, dudosa]

    assert verificacion.proporcion_de_reales(todas) == (1, 6)
    verificacion._agregar_contexto(todas)
    assert dudosa.veredicto["texto"].endswith(
        "de 6 ofertas con descuento anunciado que sí se pudieron comprobar,"
        " 1 eran descuentos reales."
    )
    assert comprobadas[0].veredicto["texto"] == "Base."
    assert dudosa.veredicto["reales_en_la_busqueda"] == 1

    # Con muy pocas comprobadas no se habla de proporciones.
    pocas = [con_veredicto("oferta_falsa"), con_veredicto("sin_referencia", "")]
    assert verificacion.proporcion_de_reales(pocas) is None
    verificacion._agregar_contexto(pocas)
    assert pocas[1].veredicto["texto"] == "Base."


def test_mercado_de_la_busqueda_exige_suficientes_productos_y_tiendas():
    from ofertas import verificacion
    from ofertas.modelos import Oferta

    def colchon(tienda, precio, nombre="Colchón doble"):
        return Oferta(tienda, tienda, nombre, "", float(precio), float(precio), f"https://{tienda}/p")

    propia = colchon("falabella", 700000)
    pocas = [colchon(f"t{i}", 500000 + i * 1000) for i in range(5)]
    assert verificacion.mercado_para(propia, [propia, *pocas]) is None

    otras = [colchon(f"t{i % 6}", 400000 + i * 20000) for i in range(21)]
    hermana = colchon("homecenter", 9000000)  # mismo dueño que Falabella: no cuenta
    usado = colchon("t1", 50000, "Colchón doble usado")  # tampoco: otra condición
    mercado = verificacion.mercado_para(propia, [propia, hermana, usado, *otras])
    assert (mercado.productos, mercado.tiendas) == (21, 6)
    assert mercado.p25 == 500000 and mercado.mediana == 600000
    assert mercado.p75 == 700000 and mercado.p90 == 760000
