"""El veredicto es lógica pura: se prueba con ofertas armadas a mano."""

import pytest

from ofertas import veredicto
from ofertas.modelos import Oferta
from ofertas.veredicto import Internacional


def oferta(precio, lista=None, tienda="falabella"):
    return Oferta(tienda, tienda.capitalize(), "Televisor 55", "SAMSUNG", precio,
                  lista or precio, f"https://{tienda}/tv")


def otras(*precios):
    return [oferta(p, tienda=f"tienda{i}") for i, p in enumerate(precios)]


def afuera(usd, coincidencia="modelo"):
    return Internacional(precio_usd=usd, trm=4000.0, coincidencia=coincidencia,
                         fuentes=["Samsung EE. UU."], ejemplo="Samsung TV")


def test_el_caso_central_precio_normal_presentado_como_oferta():
    """Lista inflada al doble para anunciar 50% sobre lo que vale en todas partes."""
    juicio = veredicto.evaluar(oferta(1589900, 3209900), otras(1589768, 1599900, 1610000))
    assert juicio.clase == "oferta_falsa"
    assert juicio.titulo == "Oferta engañosa"
    assert juicio.precio_real == 1599900
    assert juicio.descuento_anunciado_pct == 50.5
    assert abs(juicio.ahorro_real_pct) < 1
    assert juicio.lista_inflada_pct == 100.6
    assert "no hay ahorro real" in juicio.texto
    assert "inflado 101%" in juicio.texto
    assert not juicio.favorable
    assert juicio.confianza == "fuerte"


def test_descuento_real_pero_menor_que_el_anunciado():
    juicio = veredicto.evaluar(oferta(1400000, 2600000), otras(1700000, 1710000, 1690000))
    assert juicio.clase == "descuento_real"
    assert juicio.ahorro_real_pct == 17.6
    assert "Ahorras 18% de verdad, no el 46% que anuncia la tienda" in juicio.texto
    assert juicio.favorable


def test_descuento_real_con_lista_honesta_no_acusa_inflado():
    juicio = veredicto.evaluar(oferta(800000, 1000000), otras(990000, 1000000, 1010000))
    assert juicio.clase == "descuento_real"
    assert "inflado" not in juicio.texto and "no el" not in juicio.texto


def test_mas_caro_que_lo_normal_aun_con_descuento():
    juicio = veredicto.evaluar(oferta(2000000, 3000000), otras(1600000, 1650000, 1700000))
    assert juicio.clase == "sobreprecio"
    assert "Aun con el 33% de descuento anunciado, está 21% por encima" in juicio.texto


@pytest.mark.parametrize(
    ("precio", "clase"),
    [(800000, "buen_precio"), (1000000, "precio_normal"), (1050000, "precio_normal"),
     (1200000, "caro")],
)
def test_sin_descuento_anunciado_dice_si_es_buen_precio(precio, clase):
    assert veredicto.evaluar(oferta(precio), otras(1000000, 1010000, 990000)).clase == clase


def test_sin_evidencia_no_se_pronuncia_pero_avisa_del_descuento_no_comprobado():
    juicio = veredicto.evaluar(oferta(100, 200), [])
    assert juicio.clase == "sin_referencia"
    assert "anuncia 50% de descuento, pero no hay con qué comprobarlo" in juicio.texto
    assert juicio.precio_real is None
    assert veredicto.evaluar(oferta(100), []).texto.startswith("No hay evidencia")


def test_una_sola_tienda_mas_es_evidencia_limitada():
    juicio = veredicto.evaluar(oferta(1589900, 3209900), otras(1589768))
    assert juicio.clase == "oferta_falsa"
    assert juicio.confianza == "media"
    assert "evidencia es limitada" in juicio.texto


def test_variantes_de_color_sirven_cuando_falta_el_producto_identico():
    juicio = veredicto.evaluar(oferta(3000000), [], variantes=otras(4600000, 4700000))
    assert juicio.clase == "buen_precio"
    assert "misma referencia en otro color" in juicio.texto
    assert juicio.confianza == "media"
    # Con dos tiendas que tienen el producto idéntico, las variantes no se usan.
    juicio = veredicto.evaluar(oferta(3000000), otras(3000000, 3010000),
                               variantes=otras(4600000, 4700000))
    assert juicio.precio_real == 3005000


def test_historial_propio_como_evidencia():
    poco = {"veces_visto": 2, "dias_observado": 30, "mediana_vista": 500}
    assert veredicto.evaluar(oferta(100, 200), [], poco).clase == "sin_referencia"
    suficiente = {"veces_visto": 5, "dias_observado": 20, "mediana_vista": 100}
    juicio = veredicto.evaluar(oferta(100, 200), [], suficiente)
    assert juicio.clase == "oferta_falsa"
    assert "su precio habitual en esta tienda" in juicio.texto


def test_internacional_convierte_con_trm_iva_e_importacion():
    ref = afuera(100)
    assert ref.en_pesos == 400000
    assert ref.con_iva == pytest.approx(476000)
    assert ref.normal_esperado == pytest.approx(547400)
    assert ref.tope_normal == pytest.approx(618800)


def test_internacional_confiable_decide_cuando_no_hay_mercado_local():
    juicio = veredicto.evaluar(oferta(547000, 1200000), [], internacional=afuera(100, "exacto"))
    assert juicio.clase == "oferta_falsa"
    assert juicio.confianza == "fuerte"
    assert "afuera vale US$ 100.00" in juicio.texto
    barato = veredicto.evaluar(oferta(400000, 1200000), [], internacional=afuera(100, "exacto"))
    assert barato.clase == "descuento_real" and barato.favorable


def test_mismo_modelo_afuera_por_si_solo_es_evidencia_limitada():
    """Un kit con baterías y la herramienta sola comparten modelo: no basta para afirmar."""
    juicio = veredicto.evaluar(oferta(310000, 440000), [], internacional=afuera(120))
    assert juicio.clase == "descuento_real"
    assert juicio.confianza == "media"
    assert "confirma que sea la misma presentación" in juicio.texto
    # Si además hay mercado local, este manda y el precio de afuera queda como contexto.
    con_mercado = veredicto.evaluar(oferta(310000, 440000), otras(320000, 315000, 318000),
                                    internacional=afuera(120))
    assert (con_mercado.clase, con_mercado.confianza) == ("oferta_falsa", "fuerte")


def test_internacional_equivalente_no_se_presenta_como_comprobado():
    juicio = veredicto.evaluar(
        oferta(400000, 1200000), [], internacional=afuera(100, "equivalente")
    )
    assert juicio.clase == "descuento_real"
    assert juicio.titulo == "Descuento real (aproximado)"
    assert juicio.confianza == "aproximada"
    assert not juicio.favorable
    assert "Sin confirmar" in juicio.texto


def test_avisa_cuando_todo_el_mercado_local_esta_inflado_frente_al_exterior():
    """Todas las tiendas a 1.000.000 y afuera vale 100 dólares (476.000 con IVA)."""
    juicio = veredicto.evaluar(oferta(1000000, 2000000), otras(1000000, 1010000, 990000),
                               internacional=afuera(100))
    assert juicio.clase == "oferta_falsa"
    assert "en Colombia este producto cuesta 62% más de lo que se explica" in juicio.texto


def test_dice_cuando_esta_por_debajo_del_precio_internacional():
    juicio = veredicto.evaluar(oferta(450000), otras(600000, 610000, 590000),
                               internacional=afuera(100))
    assert juicio.clase == "buen_precio"
    assert "por debajo del precio internacional con IVA ($476.000)" in juicio.texto


def test_el_veredicto_es_serializable():
    datos = veredicto.evaluar(oferta(1589900, 3209900), otras(1589768, 1599900, 1610000),
                              internacional=afuera(300)).a_dict()
    assert datos["clase"] == "oferta_falsa"
    assert [e["tipo"] for e in datos["evidencias"]] == ["mercado", "internacional"]
    assert datos["evidencias"][0]["fuerza"] == "fuerte"


def test_equipos_de_la_misma_ficha_orientan_cuando_no_hay_nada_mas():
    comparables = otras(1000000, 1050000, 1100000)
    juicio = veredicto.evaluar(oferta(1040000, 2500000), [], comparables=comparables)
    assert juicio.clase == "oferta_falsa"
    assert juicio.titulo == "Oferta engañosa (aproximado)"
    assert juicio.confianza == "aproximada"
    assert not juicio.favorable
    assert "misma ficha técnica" in juicio.texto
    assert "la marca también pesa" in juicio.texto
    # Con un solo equipo comparable no se pronuncia.
    assert veredicto.evaluar(oferta(1040000, 2500000), [],
                             comparables=otras(1000000)).clase == "sin_referencia"


def test_una_sola_tienda_con_la_misma_referencia_es_evidencia_limitada():
    juicio = veredicto.evaluar(oferta(999999, 1680000), [], variantes=otras(1139775))
    assert juicio.clase == "descuento_real"
    assert juicio.confianza == "media"
    assert "de la misma referencia" in juicio.texto
    assert "evidencia es limitada" in juicio.texto


def test_el_margen_de_importacion_sale_del_arancel_y_se_puede_configurar(monkeypatch):
    monkeypatch.delenv("OFERTAS_MARGEN_IMPORTACION", raising=False)
    assert veredicto.margen_con_arancel(None) == 0.30  # categoría desconocida
    assert veredicto.margen_con_arancel(0.0) == 0.20  # portátiles: solo flete y margen
    assert veredicto.margen_con_arancel(0.40) == 0.68  # confecciones
    ropa = Internacional(precio_usd=100, trm=4000.0, coincidencia="modelo", margen=0.68)
    assert ropa.tope_normal == pytest.approx(476000 * 1.68)
    monkeypatch.setenv("OFERTAS_MARGEN_IMPORTACION", "0.25")
    assert veredicto.margen_con_arancel(0.40) == 0.25
    monkeypatch.setenv("OFERTAS_MARGEN_IMPORTACION", "mucho")
    assert veredicto.margen_con_arancel(0.0) == 0.20


MERCADO = veredicto.Mercado(productos=40, tiendas=8, p25=500000, mediana=650000, p75=800000,
                            p90=1200000)


def test_producto_generico_con_lista_fuera_del_mercado():
    """Un colchón que nadie más vende: antes $2.500.000, ahora $700.000."""
    juicio = veredicto.evaluar(oferta(700000, 2500000), [], mercado=MERCADO)
    assert juicio.clase == "oferta_falsa"
    assert juicio.titulo == "Oferta engañosa (aproximado)"
    assert juicio.confianza == "aproximada"
    assert not juicio.favorable
    assert juicio.precio_real is None
    assert juicio.lista_inflada_pct == 108.3
    assert "9 de cada 10 por menos de $1.200.000" in juicio.texto
    assert "se calcula sobre una lista fuera de rango" in juicio.texto


def test_producto_generico_sin_patron_claro_no_se_juzga_pero_se_ubica():
    # Lista dentro de lo que cobra el mercado: puede ser un descuento legítimo.
    normal = veredicto.evaluar(oferta(700000, 1000000), [], mercado=MERCADO)
    assert normal.clase == "sin_referencia"
    assert "Este precio está dentro de ese rango" in normal.texto
    # Lista altísima pero el precio también es alto: puede ser un producto superior.
    caro = veredicto.evaluar(oferta(1500000, 3000000), [], mercado=MERCADO)
    assert caro.clase == "sin_referencia"
    assert "está por encima de ese rango" in caro.texto
    barato = veredicto.evaluar(oferta(300000, 600000), [], mercado=MERCADO)
    assert "puede ser una oferta o un producto más sencillo" in barato.texto


def test_el_mercado_no_reemplaza_la_evidencia_del_mismo_producto():
    juicio = veredicto.evaluar(oferta(700000, 2500000), otras(690000, 710000, 705000),
                               mercado=MERCADO)
    assert (juicio.clase, juicio.confianza) == ("oferta_falsa", "fuerte")
    assert juicio.precio_real == 705000
    # Sin descuento anunciado no hay nada que desmentir.
    assert veredicto.evaluar(oferta(700000), [], mercado=MERCADO).clase == "sin_referencia"
