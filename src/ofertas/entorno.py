"""Carga de variables desde el archivo `.env` del proyecto."""

from __future__ import annotations

import os
from pathlib import Path

# Raíz del proyecto: este archivo vive en src/ofertas/.
RAIZ = Path(__file__).resolve().parents[2]


def cargar_env(archivo: Path | None = None) -> list[str]:
    """Lee líneas `CLAVE=valor` y las pone en el entorno. Devuelve las claves cargadas.

    Una variable ya definida en el sistema tiene prioridad sobre el archivo, y los
    valores vacíos se ignoran. Nunca imprime los valores.
    """
    archivo = archivo or RAIZ / ".env"
    try:
        lineas = archivo.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    cargadas = []
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.removeprefix("export ").strip()
        valor = valor.strip().strip("\"'")
        if clave and valor and clave not in os.environ:
            os.environ[clave] = valor
            cargadas.append(clave)
    return cargadas
