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
    juicio = veredicto.evaluar(oferta(547000, 1200000), [], internacional=afuera(100))
    assert juicio.clase == "oferta_falsa"
    assert juicio.confianza == "fuerte"
    assert "afuera vale US$ 100.00" in juicio.texto
    barato = veredicto.evaluar(oferta(400000, 1200000), [], internacional=afuera(100))
    assert barato.clase == "descuento_real" and barato.favorable


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
