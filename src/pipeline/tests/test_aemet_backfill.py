"""Tests de la descarga de relleno (spec 001-fotovoltaicas, T-16).

Solo se prueban las piezas puras: troceo de ventanas, conversión de números y
lectura de la clave. La descarga real se verificó contra AEMET el 2026-10-27.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aemet_backfill  # noqa: E402


class TestVentanas(unittest.TestCase):
    def test_un_rango_corto_es_una_ventana(self):
        self.assertEqual(
            aemet_backfill.ventanas(date(2022, 1, 1), date(2022, 1, 10)),
            [(date(2022, 1, 1), date(2022, 1, 10))],
        )

    def test_ventanas_consecutivas_y_sin_solape(self):
        tramos = aemet_backfill.ventanas(date(2022, 1, 1), date(2022, 12, 31), dias=150)

        self.assertEqual(tramos[0][0], date(2022, 1, 1))
        self.assertEqual(tramos[-1][1], date(2022, 12, 31))
        for anterior, siguiente in zip(tramos, tramos[1:]):
            self.assertEqual(siguiente[0], anterior[1] + aemet_backfill.timedelta(days=1))
        for inicio, fin in tramos:
            self.assertLessEqual((fin - inicio).days + 1, 150)

    def test_ventana_de_un_dia(self):
        tramos = aemet_backfill.ventanas(date(2026, 6, 1), date(2026, 6, 3), dias=1)
        self.assertEqual(len(tramos), 3)
        self.assertTrue(all(inicio == fin for inicio, fin in tramos))

    def test_rango_invertido(self):
        with self.assertRaises(ValueError):
            aemet_backfill.ventanas(date(2026, 6, 1), date(2022, 1, 1))

    def test_tamano_invalido(self):
        with self.assertRaises(ValueError):
            aemet_backfill.ventanas(date(2026, 6, 1), date(2026, 6, 3), dias=0)

    def test_ninguna_ventana_supera_los_seis_meses_de_aemet(self):
        for inicio, fin in aemet_backfill.ventanas(date(2022, 1, 1), date(2026, 6, 23)):
            self.assertLess((fin - inicio).days + 1, 183, f"ventana de {inicio} a {fin}")


class TestNumero(unittest.TestCase):
    def test_coma_decimal(self):
        self.assertEqual(aemet_backfill.numero("7,9"), 7.9)

    def test_cero_es_un_valor(self):
        self.assertEqual(aemet_backfill.numero("0,0"), 0.0)

    def test_ausencias_no_son_cero(self):
        for valor in (None, "", "Ip", "Acum", "s/n"):
            self.assertIsNone(aemet_backfill.numero(valor))


if __name__ == "__main__":
    unittest.main()
