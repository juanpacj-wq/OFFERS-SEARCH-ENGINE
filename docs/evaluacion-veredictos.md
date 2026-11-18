# Evaluación del veredicto por categoría

Corrida del 2026-11-18 con `scripts/evaluar_veredictos.py`, contra las tiendas reales y sin historial previo. Se miran las primeras 20 ofertas de cada búsqueda (ordenadas por precio) y, de ellas, las que anuncian descuento.

| Búsqueda | Ofertas | Con descuento | Reales | Engañosas | Más caras | Sin verificar | Comprobadas | Aproximadas | Con precio internacional | Toda la búsqueda | Tiempo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| televisor samsung 55 | 88 | 20 | 1 | 14 | 0 | 5 | 75% | 0 | 5 de 20 | 56 de 81 (69%), 7 reales | 20 s |
| computador portatil lenovo | 180 | 19 | 12 | 4 | 0 | 3 | 84% | 7 | 10 de 20 | 66 de 172 (38%), 25 reales | 14 s |
| celular samsung galaxy | 449 | 16 | 8 | 8 | 0 | 0 | 100% | 1 | 10 de 20 | 305 de 386 (79%), 75 reales | 16 s |
| taladro percutor dewalt | 84 | 9 | 4 | 0 | 1 | 4 | 56% | 0 | 7 de 20 | 9 de 28 (32%), 5 reales | 14 s |
| tenis adidas | 201 | 20 | 9 | 0 | 0 | 11 | 45% | 8 | 8 de 20 | 39 de 123 (32%), 17 reales | 17 s |
| nevera no frost | 602 | 19 | 5 | 11 | 0 | 3 | 84% | 0 | 0 de 20 | 530 de 560 (95%), 38 reales | 14 s |
| lavadora samsung | 280 | 3 | 3 | 0 | 0 | 0 | 100% | 0 | 4 de 20 | 212 de 222 (95%), 19 reales | 6 s |
| audifonos sony | 309 | 0 | 0 | 0 | 0 | 0 | n/a | 0 | 0 de 20 | 197 de 217 (91%), 11 reales | 6 s |
| morral totto | 152 | 5 | 0 | 2 | 0 | 3 | 40% | 2 | 0 de 20 | 3 de 18 (17%), 0 reales | 6 s |
| colchon doble | 542 | 20 | 0 | 0 | 0 | 20 | 0% | 0 | 0 de 20 | 222 de 525 (42%), 30 reales | 13 s |
| silla oficina | 319 | 19 | 2 | 1 | 0 | 16 | 16% | 0 | 0 de 20 | 76 de 289 (26%), 17 reales | 14 s |
| bicicleta | 487 | 10 | 0 | 0 | 0 | 10 | 0% | 0 | 0 de 20 | 45 de 313 (14%), 18 reales | 12 s |
| camiseta polo hombre | 313 | 1 | 0 | 0 | 0 | 1 | 0% | 0 | 0 de 20 | 30 de 176 (17%), 2 reales | 9 s |
| consola nintendo switch | 81 | 20 | 2 | 13 | 2 | 3 | 85% | 5 | 6 de 20 | 57 de 75 (76%), 4 reales | 6 s |
| perfume hombre | 156 | 12 | 0 | 4 | 0 | 8 | 33% | 1 | 1 de 20 | 27 de 113 (24%), 6 reales | 6 s |

**Total:** 193 ofertas con descuento anunciado; 106 (55%) se pudieron comprobar y, de esas, 46 (43%) eran descuentos reales. En todas las ofertas de las búsquedas: 1874 comprobadas de 3298, y 274 reales.

- **Comprobadas:** tienen veredicto distinto de "sin verificar".
- **Aproximadas:** su veredicto se apoya en un producto equivalente o en equipos de igual ficha técnica; están incluidas en las comprobadas.
- **Con precio internacional:** ofertas mostradas para las que se halló referencia afuera, tengan o no descuento anunciado.
- **Toda la búsqueda:** las mismas cuentas sobre todas las ofertas con descuento anunciado, no solo las 20 primeras. Ahí no se investiga el precio internacional (solo se hace para lo que se muestra), así que es el alcance del mercado local.
- **Tiempo:** búsqueda en las tiendas más verificación, sin nada en caché.
