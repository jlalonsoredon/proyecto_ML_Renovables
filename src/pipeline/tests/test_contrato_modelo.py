"""Contrato del informe que escribe el notebook (spec 002, RF-9 · CA-9.1 y CA-9.2).

El notebook deja la decisión en `src/data/modelos/sol_como_feature.json`. Este
test comprueba que el informe declara las 18 variables de producción y las rutas
de las copias del modelo, sin cargar el `.joblib` (el entorno de la puerta no
tiene `joblib`).

La parte de backend (que `model_loader.py` use la misma lista) queda pendiente
hasta que el notebook esté revisado.
"""

import json
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
INFORME = RAIZ / "src" / "data" / "modelos" / "sol_como_feature.json"

VARIABLES_SOLARES = ["sol_lag1", "tmed_lag1"]


def informe():
    return json.loads(INFORME.read_text(encoding="utf-8"))


@unittest.skipUnless(INFORME.exists(), "sin informe de ejecución del notebook")
class TestInformeDeLaDecision(unittest.TestCase):

    def test_el_informe_declara_18_variables_de_produccion(self):
        produccion = informe()["modelo"]["features_produccion"]
        self.assertEqual(len(produccion), 18)
        self.assertEqual(produccion[-2:], VARIABLES_SOLARES)

    def test_la_base_sigue_teniendo_16_variables(self):
        self.assertEqual(len(informe()["modelo"]["features_base"]), 16)

    def test_la_variante_anade_solo_las_dos_variables_solares(self):
        modelo = informe()["modelo"]
        self.assertEqual(
            modelo["features_variante"],
            modelo["features_base"] + VARIABLES_SOLARES,
        )

    def test_el_informe_registra_las_rutas_del_modelo(self):
        rutas = informe()["rutas"]
        self.assertIn("notebook", rutas)
        for etiqueta, datos in rutas.items():
            self.assertTrue(datos["ruta"].endswith("lr_eolica.joblib"), etiqueta)
            self.assertRegex(datos["sha256"] or "", r"^[0-9a-f]{64}$", etiqueta)

    def test_el_informe_registra_la_cobertura_de_las_cinco_estaciones(self):
        self.assertEqual(len(informe()["cobertura"]), 5)


if __name__ == "__main__":
    unittest.main()
