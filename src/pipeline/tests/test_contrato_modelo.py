"""Contrato de los informes que escribe el notebook (spec 002, 005 y 006).

El notebook deja tres actas en `src/data/modelos/`:

- `sol_como_feature.json`: comparación 16 → 18 de la spec 002.
- `prevision_ree_como_feature.json`: comparación 18 → 19 de la spec 005.
- `familia_como_modelo.json`: cambio de familia de la spec 006.

La producción declarada en las tres debe ser la misma. No se carga el
`.joblib`: el entorno de la puerta no tiene `joblib`.
"""

import json
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
MODELOS = RAIZ / "src" / "data" / "modelos"
INFORME_SOLAR = MODELOS / "sol_como_feature.json"
INFORME_PREVISION = MODELOS / "prevision_ree_como_feature.json"
INFORME_FAMILIA = MODELOS / "familia_como_modelo.json"

VARIABLES_SOLARES = ["sol_lag1", "tmed_lag1"]
VARIABLE_PREVISION = "eolica_prev"

FAMILIAS_CLASICAS = (
    "Linear Regression", "Ridge", "Lasso",
    "Random Forest", "XGBoost", "LightGBM",
)


def leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


@unittest.skipUnless(INFORME_SOLAR.exists(), "sin acta solar ejecutada")
class TestActaSolar(unittest.TestCase):

    def test_la_base_sigue_teniendo_16_variables(self):
        self.assertEqual(len(leer(INFORME_SOLAR)["modelo"]["features_base"]), 16)

    def test_la_variante_anade_las_dos_variables_solares(self):
        modelo = leer(INFORME_SOLAR)["modelo"]
        self.assertEqual(
            modelo["features_variante"],
            modelo["features_base"] + VARIABLES_SOLARES,
        )

    def test_la_produccion_es_la_vigente_o_la_nueva(self):
        produccion = leer(INFORME_SOLAR)["modelo"]["features_produccion"]
        self.assertIn(len(produccion), (18, 19))

    def test_el_informe_registra_las_rutas_del_modelo(self):
        rutas = leer(INFORME_SOLAR)["rutas"]
        self.assertIn("notebook", rutas)
        for etiqueta, datos in rutas.items():
            self.assertTrue(datos["ruta"].endswith("lr_eolica.joblib"), etiqueta)
            self.assertRegex(datos["sha256"] or "", r"^[0-9a-f]{64}$", etiqueta)

    def test_el_informe_registra_la_cobertura_de_las_cinco_estaciones(self):
        self.assertEqual(len(leer(INFORME_SOLAR)["cobertura"]), 5)


@unittest.skipUnless(INFORME_PREVISION.exists(),
                     "sin acta de la previsión de REE ejecutada")
class TestActaPrevision(unittest.TestCase):

    def test_la_base_es_el_modelo_vigente_de_18(self):
        self.assertEqual(
            len(leer(INFORME_PREVISION)["modelo"]["features_base"]), 18)

    def test_la_variante_anade_la_prevision_del_dia_objetivo(self):
        modelo = leer(INFORME_PREVISION)["modelo"]
        self.assertEqual(
            modelo["features_variante"],
            modelo["features_base"] + [VARIABLE_PREVISION],
        )

    def test_la_produccion_es_coherente_con_la_decision(self):
        informe = leer(INFORME_PREVISION)
        modelo = informe["modelo"]
        if informe["decision"] == "aceptado":
            self.assertEqual(modelo["features_produccion"],
                             modelo["features_variante"])
            self.assertTrue(modelo["guardado"])
        else:
            self.assertEqual(modelo["features_produccion"],
                             modelo["features_base"])
            self.assertFalse(modelo["guardado"])

    def test_la_referencia_de_la_prevision_sola_esta_declarada(self):
        referencia = leer(INFORME_PREVISION)["referencia_prevision_sola"]
        for clave in ("n", "rmse", "mae", "r2", "desde", "hasta"):
            self.assertIn(clave, referencia)
        self.assertGreater(referencia["n"], 0)
        self.assertIsNotNone(referencia["rmse"])

    def test_la_cobertura_declara_los_origenes(self):
        cobertura = leer(INFORME_PREVISION)["cobertura_prevision"]
        for clave in ("dias", "reales", "estimadas", "sin_dato", "huecos"):
            self.assertIn(clave, cobertura)
        self.assertEqual(
            cobertura["dias"],
            cobertura["reales"] + cobertura["estimadas"] + cobertura["sin_dato"],
        )

    def test_las_dos_actas_declaran_la_misma_produccion(self):
        if not INFORME_SOLAR.exists():
            self.skipTest("sin acta solar")
        self.assertEqual(
            leer(INFORME_SOLAR)["modelo"]["features_produccion"],
            leer(INFORME_PREVISION)["modelo"]["features_produccion"],
        )

    def test_el_informe_registra_rutas_y_metricas_del_test(self):
        informe = leer(INFORME_PREVISION)
        for etiqueta, datos in informe["rutas"].items():
            self.assertTrue(datos["ruta"].endswith("lr_eolica.joblib"), etiqueta)
            self.assertRegex(datos["sha256"] or "", r"^[0-9a-f]{64}$", etiqueta)
        for clave in ("rmse", "mae", "r2", "dias", "desde", "hasta"):
            self.assertIn(clave, informe["metricas_test"])


@unittest.skipUnless(INFORME_FAMILIA.exists(),
                     "sin acta de la familia del modelo ejecutada")
class TestActaFamilia(unittest.TestCase):
    """Spec 006: la producción puede dejar de ser LinearRegression."""

    def test_la_base_es_linear_regression(self):
        modelo = leer(INFORME_FAMILIA)["modelo"]
        self.assertEqual(modelo["familia_base"], "Linear Regression")

    def test_la_variante_es_una_familia_clasica(self):
        familia = leer(INFORME_FAMILIA)["modelo"]["familia_variante"]
        self.assertIn(familia, FAMILIAS_CLASICAS)

    def test_la_produccion_es_coherente_con_la_decision(self):
        informe = leer(INFORME_FAMILIA)
        modelo = informe["modelo"]
        if informe["decision"] == "aceptado":
            self.assertEqual(modelo["familia_produccion"],
                             modelo["familia_variante"])
        else:
            self.assertEqual(modelo["familia_produccion"], "Linear Regression")
        self.assertEqual(informe["decision"], modelo["decision"])

    def test_declara_los_cuatro_folds_y_sus_metricas(self):
        informe = leer(INFORME_FAMILIA)
        self.assertEqual(len(informe["folds"]), 4)
        for fold in informe["folds"]:
            if fold["omitido"]:
                continue
            for nombre in ("base", "variante"):
                for clave in ("rmse", "mae", "r2"):
                    self.assertIn(clave, fold[nombre])

    def test_las_columnas_son_las_del_acta_de_prevision(self):
        if not INFORME_PREVISION.exists():
            self.skipTest("sin acta de previsión")
        self.assertEqual(
            leer(INFORME_FAMILIA)["modelo"]["features_produccion"],
            leer(INFORME_PREVISION)["modelo"]["features_produccion"],
        )

    def test_declara_metricas_globales_del_test_y_rutas(self):
        informe = leer(INFORME_FAMILIA)
        for nombre in ("base", "variante"):
            for clave in ("n", "rmse", "mae", "r2"):
                self.assertIn(clave, informe["metricas_globales"][nombre])
        for clave in ("rmse", "mae", "r2", "dias", "desde", "hasta"):
            self.assertIn(clave, informe["metricas_test"])
        for etiqueta, datos in informe["rutas"].items():
            self.assertTrue(datos["ruta"].endswith("lr_eolica.joblib"), etiqueta)
            self.assertRegex(datos["sha256"] or "", r"^[0-9a-f]{64}$", etiqueta)

    def test_el_preprocesado_declarado_coincide_con_la_familia(self):
        modelo = leer(INFORME_FAMILIA)["modelo"]
        self.assertIsInstance(modelo["usa_scaler"], bool)
        if modelo["familia_produccion"] in ("Linear Regression", "Ridge", "Lasso"):
            self.assertTrue(modelo["usa_scaler"])
        else:
            self.assertFalse(modelo["usa_scaler"])


if __name__ == "__main__":
    unittest.main()
