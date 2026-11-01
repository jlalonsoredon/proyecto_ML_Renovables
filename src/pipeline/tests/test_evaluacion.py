"""Tests de la lógica pura de evaluación (spec 002, RF-5, RF-6 y RF-9).

Se ejecutan con la biblioteca estándar: `python -m unittest discover`.
La puerta real del proyecto es `node --test`, que lanza esta suite (gate.test.mjs).
"""

import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evaluacion  # noqa: E402


# ─────────────────────────────────────────────
# Utilidades de los tests
# ─────────────────────────────────────────────

def serie_diaria(desde: date, hasta: date) -> list[str]:
    """Fechas ISO consecutivas, de `desde` a `hasta` incluidas."""
    dias, cursor = [], desde
    while cursor <= hasta:
        dias.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return dias


def folds_de_ejemplo():
    return [
        {"año": 2023, "train": list(range(0, 10)), "test": list(range(10, 20)),
         "omitido": False, "motivo": None},
        {"año": 2024, "train": list(range(0, 20)), "test": list(range(20, 30)),
         "omitido": False, "motivo": None},
        {"año": 2025, "train": list(range(0, 30)), "test": list(range(30, 40)),
         "omitido": False, "motivo": None},
        {"año": 2026, "train": list(range(0, 40)), "test": list(range(40, 45)),
         "omitido": False, "motivo": None},
    ]


def decision_de(retorno: dict) -> bool:
    return retorno["aceptado"]


# ─────────────────────────────────────────────
# RF-5 — Folds cronológicos
# ─────────────────────────────────────────────

class TestWalkForwardFolds(unittest.TestCase):

    def setUp(self):
        self.fechas = serie_diaria(date(2022, 1, 1), date(2026, 10, 25))
        self.folds = evaluacion.walk_forward_folds(self.fechas, date(2026, 10, 31))

    def test_cuatro_folds_anuales(self):
        self.assertEqual([f["año"] for f in self.folds], [2023, 2024, 2025, 2026])

    def test_ningun_fold_se_omite_con_datos_completos(self):
        self.assertTrue(all(not f["omitido"] for f in self.folds))

    def test_el_entrenamiento_es_siempre_anterior_a_la_prueba(self):
        for fold in self.folds:
            self.assertLess(max(fold["train"]), min(fold["test"]))

    def test_los_folds_no_se_solapan(self):
        vistos = []
        for fold in self.folds:
            self.assertFalse(set(fold["test"]) & set(vistos))
            vistos.extend(fold["test"])

    def test_el_primer_fold_entrena_con_el_primer_ano(self):
        primer = self.folds[0]
        self.assertEqual(primer["train"][0], "2022-01-01")
        self.assertEqual(primer["train"][-1], "2022-12-31")

    def test_el_ultimo_fold_usa_el_ano_en_curso_incompleto(self):
        ultimo = self.folds[-1]
        self.assertEqual(ultimo["test"][0], "2026-01-01")
        self.assertEqual(ultimo["test"][-1], "2026-10-25")

    def test_fold_con_entrenamiento_corto_se_omite_con_motivo(self):
        folds = evaluacion.walk_forward_folds(self.fechas, date(2026, 10, 31), minimo_train=400)
        omitidos = [f for f in folds if f["omitido"]]
        self.assertTrue(omitidos)
        self.assertIn("entrenamiento", omitidos[0]["motivo"])

    def test_fold_con_prueba_corta_se_omite_con_motivo(self):
        folds = evaluacion.walk_forward_folds(self.fechas, date(2026, 10, 31), minimo_test=500)
        omitidos = [f for f in folds if f["omitido"]]
        self.assertTrue(omitidos)
        self.assertIn("prueba", omitidos[0]["motivo"])

    def test_el_orden_de_entrada_no_cambia_el_resultado(self):
        desordenadas = list(reversed(self.fechas))
        folds = evaluacion.walk_forward_folds(desordenadas, date(2026, 10, 31))
        self.assertEqual(folds, self.folds)

    def test_serie_vacia_lanza_error(self):
        with self.assertRaises(ValueError):
            evaluacion.walk_forward_folds([], date(2026, 10, 31))

    def test_sin_anos_completos_devuelve_lista_vacia(self):
        folds = evaluacion.walk_forward_folds(serie_diaria(date(2026, 1, 1), date(2026, 6, 1)),
                                              date(2026, 10, 31))
        self.assertEqual(folds, [])

    def test_dos_llamadas_dan_el_mismo_resultado(self):
        segundo = evaluacion.walk_forward_folds(self.fechas, date(2026, 10, 31))
        self.assertEqual(self.folds, segundo)


# ─────────────────────────────────────────────
# RF-6 — Criterio de aceptación
# ─────────────────────────────────────────────

class TestCriterioAceptacion(unittest.TestCase):

    BASE = [1000.0, 1000.0, 1000.0, 1000.0]

    def test_tres_de_cuatro_acepta(self):
        variante = [900.0, 900.0, 900.0, 1100.0]
        self.assertTrue(decision_de(evaluacion.criterio_aceptacion(self.BASE, variante)))

    def test_dos_de_cuatro_rechaza(self):
        variante = [900.0, 900.0, 1100.0, 1100.0]
        self.assertFalse(decision_de(evaluacion.criterio_aceptacion(self.BASE, variante)))

    def test_cuatro_de_cuatro_acepta(self):
        variante = [900.0, 900.0, 900.0, 900.0]
        self.assertTrue(decision_de(evaluacion.criterio_aceptacion(self.BASE, variante)))

    def test_empate_no_cuenta_como_mejora(self):
        variante = [1000.0, 1000.0, 900.0, 900.0]
        resultado = evaluacion.criterio_aceptacion(self.BASE, variante)
        self.assertEqual(resultado["mejoras"], 2)
        self.assertFalse(resultado["aceptado"])

    def test_fold_omitido_impide_decidir(self):
        variante = [900.0, 900.0, 900.0, None]
        resultado = evaluacion.criterio_aceptacion(self.BASE, variante)
        self.assertFalse(resultado["aceptado"])
        self.assertIn("folds insuficientes", resultado["motivo"])

    def test_longitudes_distintas_lanzan_error(self):
        with self.assertRaises(ValueError):
            evaluacion.criterio_aceptacion(self.BASE, [900.0, 900.0])

    def test_sin_folds_lanza_error(self):
        with self.assertRaises(ValueError):
            evaluacion.criterio_aceptacion([], [])

    def test_devuelve_el_detalle_por_fold(self):
        variante = [900.0, 900.0, 900.0, 1100.0]
        resultado = evaluacion.criterio_aceptacion(self.BASE, variante)
        self.assertEqual(len(resultado["detalle"]), 4)
        self.assertTrue(resultado["detalle"][0]["mejora"])
        self.assertFalse(resultado["detalle"][3]["mejora"])

    def test_minimo_de_folds_configurable(self):
        variante = [900.0, 900.0, 1100.0, 1100.0]
        self.assertTrue(decision_de(evaluacion.criterio_aceptacion(self.BASE, variante, minimo=2)))


# ─────────────────────────────────────────────
# RF-9 — Resumen para imprimir y para el JSON
# ─────────────────────────────────────────────

class TestResumenFolds(unittest.TestCase):

    def setUp(self):
        self.folds = folds_de_ejemplo()
        self.metricas = {
            "base": {"rmse": [10.0, 20.0, 30.0, 40.0], "r2": [0.7, 0.7, 0.7, 0.7]},
            "variante": {"rmse": [9.0, 19.0, 29.0, 45.0], "r2": [0.8, 0.8, 0.8, 0.6]},
        }
        self.decision = evaluacion.criterio_aceptacion(
            self.metricas["base"]["rmse"], self.metricas["variante"]["rmse"])
        self.cobertura = {"3469A": {"sol": {"missing_pct": 0.1, "max_gap_days": 1}}}

    def test_estructura_completa(self):
        informe = evaluacion.resumen_folds(self.folds, self.metricas, self.decision,
                                           self.cobertura, date(2026, 10, 31))
        for clave in ("fecha_ejecucion", "folds", "criterio", "cobertura", "decision"):
            self.assertIn(clave, informe)
        self.assertEqual(informe["fecha_ejecucion"], "2026-10-31")

    def test_un_fold_por_ano_con_sus_metricas(self):
        informe = evaluacion.resumen_folds(self.folds, self.metricas, self.decision,
                                           self.cobertura, date(2026, 10, 31))
        self.assertEqual([f["año"] for f in informe["folds"]], [2023, 2024, 2025, 2026])
        self.assertEqual(informe["folds"][0]["base"]["rmse"], 10.0)
        self.assertEqual(informe["folds"][0]["variante"]["r2"], 0.8)

    def test_fold_omitido_aparece_con_motivo(self):
        folds = [dict(f) for f in self.folds]
        folds[1] = {"año": 2024, "train": [], "test": [], "omitido": True,
                    "motivo": "entrenamiento insuficiente"}
        metricas = {"base": {"rmse": [10.0, None, 30.0, 40.0], "r2": [0.7, None, 0.7, 0.7]},
                    "variante": {"rmse": [9.0, None, 29.0, 45.0], "r2": [0.8, None, 0.8, 0.6]}}
        informe = evaluacion.resumen_folds(folds, metricas, self.decision,
                                           self.cobertura, date(2026, 10, 31))
        self.assertTrue(informe["folds"][1]["omitido"])
        self.assertIn("insuficiente", informe["folds"][1]["motivo"])

    def test_es_serializable_a_json(self):
        informe = evaluacion.resumen_folds(self.folds, self.metricas, self.decision,
                                           self.cobertura, date(2026, 10, 31))
        json.dumps(informe)

    def test_sin_folds_lanza_error(self):
        with self.assertRaises(ValueError):
            evaluacion.resumen_folds([], self.metricas, self.decision,
                                     self.cobertura, date(2026, 10, 31))

    def test_longitudes_incoherentes_lanzan_error(self):
        metricas = {"base": {"rmse": [1.0], "r2": [0.7]},
                    "variante": {"rmse": [1.0, 2.0], "r2": [0.7, 0.7]}}
        with self.assertRaises(ValueError):
            evaluacion.resumen_folds(self.folds, metricas, self.decision,
                                     self.cobertura, date(2026, 10, 31))


if __name__ == "__main__":
    unittest.main()
