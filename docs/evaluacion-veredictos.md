# Evaluación del veredicto por categoría

Corrida del 2026-11-18 con `scripts/evaluar_veredictos.py`, contra las tiendas reales y sin historial previo. Se miran las primeras 20 ofertas de cada búsqueda (ordenadas por precio) y, de ellas, las que anuncian descuento.

| Búsqueda | Ofertas | Con descuento | Reales | Engañosas | Más caras | Sin verificar | Comprobadas | Aproximadas | Con precio internacional | Tiempo |
|---|---|---|---|---|---|---|---|---|---|---|
| televisor samsung 55 | 83 | 20 | 2 | 12 | 0 | 6 | 70% | 0 | 8 de 20 | 15 s |
| computador portatil lenovo | 181 | 19 | 12 | 4 | 0 | 3 | 84% | 7 | 8 de 20 | 6 s |
| celular samsung galaxy | 455 | 16 | 6 | 9 | 1 | 0 | 100% | 1 | 11 de 20 | 5 s |
| taladro percutor dewalt | 84 | 9 | 4 | 0 | 1 | 4 | 56% | 0 | 7 de 20 | 5 s |
| tenis adidas | 202 | 20 | 9 | 0 | 0 | 11 | 45% | 8 | 8 de 20 | 5 s |
| nevera no frost | 600 | 19 | 5 | 11 | 0 | 3 | 84% | 0 | 0 de 20 | 6 s |
| lavadora samsung | 280 | 3 | 3 | 0 | 0 | 0 | 100% | 0 | 4 de 20 | 6 s |
| audifonos sony | 261 | 0 | 0 | 0 | 0 | 0 | n/a | 0 | 0 de 20 | 8 s |
| morral totto | 146 | 5 | 0 | 0 | 0 | 5 | 0% | 0 | 2 de 20 | 9 s |
| colchon doble | 514 | 20 | 0 | 0 | 0 | 20 | 0% | 0 | 0 de 20 | 10 s |
| silla oficina | 308 | 19 | 2 | 1 | 0 | 16 | 16% | 0 | 0 de 20 | 10 s |
| bicicleta | 440 | 10 | 0 | 0 | 0 | 10 | 0% | 0 | 0 de 20 | 9 s |
| camiseta polo hombre | 316 | 1 | 0 | 0 | 0 | 1 | 0% | 0 | 0 de 20 | 9 s |
| consola nintendo switch | 81 | 20 | 2 | 13 | 2 | 3 | 85% | 5 | 6 de 20 | 8 s |
| perfume hombre | 157 | 12 | 0 | 4 | 0 | 8 | 33% | 1 | 1 de 20 | 5 s |

**Total:** 193 ofertas con descuento anunciado; 103 (53%) se pudieron comprobar y, de esas, 45 (44%) eran descuentos reales.

- **Comprobadas:** tienen veredicto distinto de "sin verificar".
- **Aproximadas:** su veredicto se apoya en un producto equivalente o en equipos de igual ficha técnica; están incluidas en las comprobadas.
- **Con precio internacional:** ofertas mostradas para las que se halló referencia afuera, tengan o no descuento anunciado.
- **Tiempo:** búsqueda en las tiendas más verificación, sin nada en caché.
