# Evaluación del veredicto por categoría

Corrida del 2026-11-18 con `scripts/evaluar_veredictos.py`, contra las tiendas reales y sin historial previo, usando además el archivo de Internet. Se miran las primeras 20 ofertas de cada búsqueda (ordenadas por precio) y, de ellas, las que anuncian descuento.

| Búsqueda | Ofertas | Con descuento | Reales | Engañosas | Más caras | Sin verificar | Comprobadas | Aproximadas | Con precio internacional | Toda la búsqueda | Tiempo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| televisor samsung 55 | 88 | 20 | 1 | 14 | 0 | 5 | 75% | 0 | 4 de 20 | 56 de 81 (69%), 7 reales | 25 s |
| computador portatil lenovo | 181 | 19 | 12 | 4 | 1 | 2 | 89% | 7 | 10 de 20 | 68 de 173 (39%), 26 reales | 17 s |
| celular samsung galaxy | 445 | 16 | 8 | 7 | 1 | 0 | 100% | 1 | 10 de 20 | 304 de 380 (80%), 73 reales | 27 s |
| taladro percutor dewalt | 84 | 9 | 4 | 0 | 1 | 4 | 56% | 0 | 7 de 20 | 9 de 28 (32%), 5 reales | 26 s |
| tenis adidas | 185 | 20 | 8 | 1 | 0 | 11 | 45% | 6 | 8 de 20 | 39 de 114 (34%), 16 reales | 31 s |
| nevera no frost | 601 | 19 | 6 | 11 | 0 | 2 | 89% | 0 | 0 de 20 | 529 de 559 (95%), 39 reales | 18 s |
| lavadora samsung | 279 | 3 | 3 | 0 | 0 | 0 | 100% | 0 | 4 de 20 | 211 de 221 (95%), 18 reales | 9 s |
| audifonos sony | 309 | 0 | 0 | 0 | 0 | 0 | n/a | 0 | 0 de 20 | 197 de 217 (91%), 11 reales | 6 s |
| morral totto | 152 | 6 | 1 | 2 | 0 | 3 | 50% | 2 | 0 de 20 | 4 de 18 (22%), 1 reales | 15 s |
| colchon doble | 543 | 20 | 0 | 0 | 0 | 20 | 0% | 0 | 0 de 20 | 222 de 525 (42%), 30 reales | 28 s |
| silla oficina | 318 | 19 | 2 | 1 | 0 | 16 | 16% | 0 | 0 de 20 | 71 de 287 (25%), 17 reales | 17 s |
| bicicleta | 483 | 9 | 1 | 1 | 0 | 7 | 22% | 0 | 0 de 20 | 51 de 307 (17%), 19 reales | 25 s |
| camiseta polo hombre | 314 | 1 | 0 | 1 | 0 | 0 | 100% | 0 | 0 de 20 | 30 de 175 (17%), 2 reales | 22 s |
| consola nintendo switch | 81 | 20 | 1 | 13 | 3 | 3 | 85% | 5 | 7 de 20 | 57 de 75 (76%), 3 reales | 23 s |
| perfume hombre | 157 | 14 | 0 | 6 | 1 | 7 | 50% | 2 | 2 de 20 | 34 de 119 (29%), 6 reales | 23 s |

**Total:** 195 ofertas con descuento anunciado; 115 (59%) se pudieron comprobar y, de esas, 47 (41%) eran descuentos reales. En todas las ofertas de las búsquedas: 1882 comprobadas de 3279, y 273 reales.

- **Comprobadas:** tienen veredicto distinto de "sin verificar".
- **Aproximadas:** su veredicto se apoya en un producto equivalente o en equipos de igual ficha técnica; están incluidas en las comprobadas.
- **Con precio internacional:** ofertas mostradas para las que se halló referencia afuera, tengan o no descuento anunciado.
- **Toda la búsqueda:** las mismas cuentas sobre todas las ofertas con descuento anunciado, no solo las 20 primeras. Ahí no se investiga el precio internacional (solo se hace para lo que se muestra), así que es el alcance del mercado local.
- **Tiempo:** búsqueda en las tiendas más verificación, sin nada en caché.
