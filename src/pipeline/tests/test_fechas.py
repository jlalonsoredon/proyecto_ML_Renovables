"""Tests de la lógica pura de fechas (spec 002, RF-1 y RF-2).

Se ejecutan con la biblioteca estándar: `python -m unittest discover`.
La puerta real del proyecto es `node --test`, que lanza esta suite (gate.test.mjs).
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fechas  # noqa: E402


# ─────────────────────────────────────────────
# RF-2 — Instante UTC → día natural peninsular
# ─────────────────────────────────────────────

class TestFechaMadrid(unittest.TestCase):

    def test_invierno_medianoche_peninsular(self):
        # 23:00Z de invierno (UTC+1) ya es la medianoche del día siguiente
        self.assertEqual(fechas.fecha_madrid("2026-01-15T23:00:00Z"), "2026-01-16")

    def test_verano_medianoche_peninsular(self):
        # 22:00Z de verano (UTC+2) ya es la medianoche del día siguiente
        self.assertEqual(fechas.fecha_madrid("2026-07-15T22:00:00Z"), "2026-07-16")

    def test_verano_tarde_sigue_siendo_el_mismo_dia(self):
        self.assertEqual(fechas.fecha_madrid("2026-07-15T12:00:00Z"), "2026-07-15")

    def test_invierno_tarde_sigue_siendo_el_mismo_dia(self):
        self.assertEqual(fechas.fecha_madrid("2026-01-15T12:00:00Z"), "2026-01-15")

    def test_ultimo_domingo_marzo_22z_ya_en_utc2(self):
        # El cambio a UTC+2 ocurre a las 01:00Z: a las 22:00Z del domingo 29 ya aplica
        self.assertEqual(fechas.fecha_madrid("2026-03-29T22:00:00Z"), "2026-03-30")

    def test_ultimo_domingo_marzo_antes_de_las_01z_sigue_en_utc1(self):
        # Justo antes del cambio: 00:00Z del domingo 29 aún es UTC+1
        self.assertEqual(fechas.fecha_madrid("2026-03-29T00:00:00Z"), "2026-03-29")

    def test_dia_anterior_al_cambio_de_marzo_en_utc1(self):
        self.assertEqual(fechas.fecha_madrid("2026-03-28T22:00:00Z"), "2026-03-28")

    def test_ultimo_domingo_octubre_22z_ya_en_utc1(self):
        # El cambio a UTC+1 ocurre a las 01:00Z: a las 22:00Z del 25 ya aplica
        self.assertEqual(fechas.fecha_madrid("2026-10-25T22:00:00Z"), "2026-10-25")

    def test_dia_anterior_al_cambio_de_octubre_en_utc2(self):
        self.assertEqual(fechas.fecha_madrid("2026-10-24T22:00:00Z"), "2026-10-25")

    def test_cambio_de_ano(self):
        self.assertEqual(fechas.fecha_madrid("2025-12-31T23:00:00Z"), "2026-01-01")

    def test_bisiesto(self):
        self.assertEqual(fechas.fecha_madrid("2024-02-28T23:00:00Z"), "2024-02-29")

    def test_acepta_datetime(self):
        from datetime import datetime
        self.assertEqual(fechas.fecha_madrid(datetime(2026, 1, 15, 23, 0)), "2026-01-16")

    def test_entrada_invalida_lanza_error(self):
        with self.assertRaises(ValueError):
            fechas.fecha_madrid("no es una fecha")

    def test_entrada_vacia_lanza_error(self):
        with self.assertRaises(ValueError):
            fechas.fecha_madrid("")


# ─────────────────────────────────────────────
# RF-1 — Rango pendiente de descarga
# ─────────────────────────────────────────────

class TestVentanaDescarga(unittest.TestCase):

    def test_bd_al_dia_no_hay_nada_que_descargar(self):
        self.assertIsNone(fechas.ventana_descarga(date(2026, 11, 1), date(2026, 10, 29)))

    def test_fecha_futura_en_bd_no_genera_rango_invertido(self):
        self.assertIsNone(fechas.ventana_descarga(date(2026, 11, 1), date(2026, 10, 31)))

    def test_hueco_de_varios_dias(self):
        inicio, fin = fechas.ventana_descarga(date(2026, 11, 1), date(2026, 10, 25))
        self.assertEqual(inicio, date(2026, 10, 26))
        self.assertEqual(fin, date(2026, 10, 29))

    def test_fin_nunca_supera_el_retraso(self):
        _, fin = fechas.ventana_descarga(date(2026, 11, 1), None)
        self.assertEqual(fin, date(2026, 10, 29))

    def test_bd_vacia_arranca_en_el_inicio_del_estudio(self):
        inicio, _ = fechas.ventana_descarga(date(2026, 11, 1), None)
        self.assertEqual(inicio, date(2022, 1, 1))

    def test_retraso_personalizado(self):
        _, fin = fechas.ventana_descarga(date(2026, 11, 1), None, retraso=5)
        self.assertEqual(fin, date(2026, 10, 27))

    def test_acepta_fechas_en_texto(self):
        inicio, fin = fechas.ventana_descarga("2026-11-01", "2026-10-25")
        self.assertEqual((inicio, fin), (date(2026, 10, 26), date(2026, 10, 29)))

    def test_inicio_de_estudio_personalizado(self):
        inicio, _ = fechas.ventana_descarga(date(2026, 11, 1), None, inicio_estudio=date(2023, 1, 1))
        self.assertEqual(inicio, date(2023, 1, 1))

    def test_dos_llamadas_dan_el_mismo_rango(self):
        primero = fechas.ventana_descarga(date(2026, 11, 1), date(2026, 10, 25))
        segundo = fechas.ventana_descarga(date(2026, 11, 1), date(2026, 10, 25))
        self.assertEqual(primero, segundo)


if __name__ == "__main__":
    unittest.main()
