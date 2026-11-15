"""Redacción de credenciales en mensajes de error y trazas.

Las excepciones de `requests` incluyen la URL completa; si la clave viaja como
parámetro de consulta, termina en logs y resúmenes de captura. Este módulo
sustituye tanto los parámetros sensibles como los valores conocidos.
"""

import re
from urllib.parse import quote

_PARAMETRO_SENSIBLE = re.compile(
    r"(?i)(?P<param>[\"']?\b(?:api[_-]?key|esios[_-]?token|access[_-]?token|x-api-key|token)\b"
    r"[\"']?\s*[=:]\s*[\"']?)"
    r"(?P<valor>[^\s&,'\"<>}]+)"
)


def redact_secrets(value, *secrets) -> str:
    """Devuelve el texto sin claves conocidas ni parámetros sensibles."""
    if value is None:
        return ""

    texto = str(value)
    for secret in secrets:
        if not secret:
            continue
        texto = texto.replace(str(secret), "[REDACTED]")
        encoded = quote(str(secret), safe="")
        if encoded != str(secret):
            texto = texto.replace(encoded, "[REDACTED]")

    return _PARAMETRO_SENSIBLE.sub(
        lambda match: f"{match.group('param')}[REDACTED]", texto
    )
