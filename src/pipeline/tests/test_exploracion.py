"""Estudio de Pearson de las variables nuevas (spec 006, RF-1).

Lógica pura con la biblioteca estándar: la puerta `node --test` no instala
pandas ni numpy. El notebook le pasa las columnas ya limpias; aquí solo se
decide qué es un par válido y cuándo una correlación no se puede calcular.
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src" / "pipeline"))

import exploracion  # noqa: E402


class TestCorrelacionPearson(unittest.TestCase):

    def test_correlacion_perfecta_positiva(self):
        resultado = exploracion.correlacion_pearson([1, 2, 3], [2, 4, 6])
        self.assertEqual(resultado["n"], 3)
        self.assertAlmostEqual(resultado["r"], 1.0)

    def test_correlacion_perfecta_negativa(self):
        resultado = exploracion.correlacion_pearson([1, 2, 3], [3, 2, 1])
        self.assertAlmostEqual(resultado["r"], -1.0)

    def test_valor_conocido(self):
        # dx=[-1.5,-0.5,0.5,1.5], dy=[-1.5,0.5,-0.5,1.5] → r = 4/5
        resultado = exploracion.correlacion_pearson([1, 2, 3, 4], [1, 3, 2, 4])
        self.assertAlmostEqual(resultado["r"], 0.8)

    def test_los_pares_incompletos_no_cuentan(self):
        resultado = exploracion.correlacion_pearson(
            [1, None, 3, 4], [1, 2, None, 4])
        self.assertEqual(resultado["n"], 2)
        self.assertAlmostEqual(resultado["r"], 1.0)

    def test_nan_se_trata_como_ausente(self):
        resultado = exploracion.correlacion_pearson(
            [1.0, float("nan"), 3.0], [1.0, 2.0, 3.0])
        self.assertEqual(resultado["n"], 2)
        self.assertAlmostEqual(resultado["r"], 1.0)

    def test_menos_de_dos_pares_no_tiene_correlacion(self):
        for xs, ys, esperado in (
            ([], [], 0),
            ([1.0], [2.0], 1),
            ([1.0, None], [None, 2.0], 0),
        ):
            with self.subTest(xs=xs, ys=ys):
                self.assertEqual(
                    exploracion.correlacion_pearson(xs, ys),
                    {"n": esperado, "r": None},
                )

    def test_una_serie_constante_no_tiene_correlacion(self):
        resultado = exploracion.correlacion_pearson([2, 2, 2], [1, 2, 3])
        self.assertEqual(resultado["n"], 3)
        self.assertIsNone(resultado["r"])

    def test_longitudes_distintas_lanzan_error(self):
        with self.assertRaises(ValueError):
            exploracion.correlacion_pearson([1, 2], [1, 2, 3])

    def test_el_cero_es_un_valor_valido(self):
        resultado = exploracion.correlacion_pearson([0, 1, 2], [0, 1, 2])
        self.assertEqual(resultado["n"], 3)
        self.assertAlmostEqual(resultado["r"], 1.0)

    def test_acepta_iterables_que_no_se_pueden_evaluar_como_booleano(self):
        """Una Serie de pandas lanza al hacer `or`: se debe iterar, no evaluar."""

        class SerieComoPandas:
            def __init__(self, valores):
                self.valores = list(valores)

            def __iter__(self):
                return iter(self.valores)

            def __bool__(self):
                raise ValueError("el valor booleano es ambiguo")

        resultado = exploracion.correlacion_pearson(
            SerieComoPandas([1, 2, 3]), SerieComoPandas([2, 4, 6]))
        self.assertEqual(resultado["n"], 3)
        self.assertAlmostEqual(resultado["r"], 1.0)

    def test_dos_ejecuciones_dan_lo_mismo(self):
        primera = exploracion.correlacion_pearson([1, 2, 3, 4], [4, 2, 3, 1])
        segunda = exploracion.correlacion_pearson([1, 2, 3, 4], [4, 2, 3, 1])
        self.assertEqual(primera, segunda)


if __name__ == "__main__":
    unittest.main()
