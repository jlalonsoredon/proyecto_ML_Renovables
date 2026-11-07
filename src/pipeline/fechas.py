"""Lógica pura de fechas del proyecto (spec 002-sol-feature-eolica, RF-1 y RF-2).

Sin E/S, sin pandas y sin `zoneinfo`: el entorno no dispone de `tzdata`, así que
la regla europea de cambio de hora se calcula aquí. Solo biblioteca estándar para
que la suite se pueda ejecutar sin instalar nada (constitución, principio 4).

La fecha es el punto donde se juega la corrección del join entre la generación
de REE (timestamps UTC) y las observaciones de AEMET (día natural): un desfase
de un día falsea todas las métricas sin dejar rastro.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

# Mismo inicio que `solar.study_window` y el notebook.
INICIO_ESTUDIO = date(2022, 1, 1)

# AEMET publica con retraso: no se piden los últimos días. Medido en 2026-11:
# cuatro días, no tres (plan 003, decisión 14); con tres se pide a diario un día
# que todavía no puede existir.
RETRASO_PUBLICACION_DIAS = 4


class FechaError(ValueError):
    """El valor recibido no es una fecha o un instante utilizable."""


# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────

def a_fecha(valor) -> date:
    """Convierte date, datetime o texto ISO a fecha. Error explícito si no lo es."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    if not texto:
        raise FechaError("fecha vacía: se esperaba una fecha 'YYYY-MM-DD' o un instante ISO")

    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").date()
    except ValueError as error:
        raise FechaError(f"fecha inválida: {valor!r} (se esperaba 'YYYY-MM-DD')") from error


def _ultimo_domingo(ano: int, mes: int) -> date:
    """Último domingo del mes: base del cambio de hora europeo."""
    primer_dia_siguiente = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    ultimo_dia = primer_dia_siguiente - timedelta(days=1)
    return ultimo_dia - timedelta(days=(ultimo_dia.weekday() + 1) % 7)


def _desfase_horas(instante: datetime) -> int:
    """UTC+2 entre el último domingo de marzo y el de octubre (01:00 UTC); UTC+1 el resto."""
    inicio_verano = datetime.combine(_ultimo_domingo(instante.year, 3), time(1))
    fin_verano = datetime.combine(_ultimo_domingo(instante.year, 10), time(1))
    return 2 if inicio_verano <= instante < fin_verano else 1


# ─────────────────────────────────────────────
# RF-2 — Instante UTC → día natural peninsular
# ─────────────────────────────────────────────

def fecha_madrid(instante) -> str:
    """Día natural peninsular ('YYYY-MM-DD') de un instante UTC.

    `23:00Z` de invierno y `22:00Z` de verano son la medianoche del día
    siguiente: cortar la fecha en UTC desplazaría un día entero.
    """
    if isinstance(instante, datetime):
        momento = instante.replace(tzinfo=None)
    else:
        texto = str(instante).strip()
        if not texto:
            raise FechaError("instante vacío: se esperaba una marca de tiempo ISO")
        try:
            momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError as error:
            raise FechaError(f"instante inválido: {instante!r} (se esperaba ISO 8601)") from error
        momento = momento.replace(tzinfo=None)

    local = momento + timedelta(hours=_desfase_horas(momento))
    return local.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# RF-1 — Rango pendiente de descarga
# ─────────────────────────────────────────────

def ventana_descarga(hoy, ultima_fecha_bd,
                     inicio_estudio: date = INICIO_ESTUDIO,
                     retraso: int = RETRASO_PUBLICACION_DIAS):
    """Rango (inicio, fin) que falta descargar, o None si no falta nada.

    No trocea: el troceo en ventanas de 150 días lo hace
    `aemet_backfill.ventanas()`, que ya está probado y respeta el límite de AEMET.
    Aquí solo se decide desde dónde hasta dónde, que es la parte que depende de `hoy`.
    """
    if retraso < 0:
        raise ValueError(f"el retraso no puede ser negativo: {retraso}")

    fin = a_fecha(hoy) - timedelta(days=retraso)
    inicio = a_fecha(inicio_estudio) if ultima_fecha_bd is None else a_fecha(ultima_fecha_bd) + timedelta(days=1)

    if inicio > fin:
        return None
    return inicio, fin
