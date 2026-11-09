"""Integridad de las tablas de observación (spec 004, RF-5; CA-5.1).

Comprobación estática del notebook: las únicas funciones que escriben en
`generacion` y `aemet_diario` son las dos descargas que ya existían. Las celdas
nuevas de la spec 004 escriben solo en las tablas del archivo de previsiones y de
la predicción propia.

No se ejecuta el notebook: se lee su JSON. Así la puerta no necesita red ni
pandas y el fallo es legible (una celda nueva que intente tocar la observación).
"""

import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src" / "pipeline"))

NOTEBOOK = RAIZ / "src" / "notebooks" / "main.ipynb"

MARCADORES = {
    "captura": "CAPTURA DE PREVISIONES (spec 004",
    "relleno_ree": "RELLENO HISTÓRICO (spec 004",
    "captura_ree": "CAPTURA REE (spec 004",
    "mapa": "MAPA DE ORÍGENES (spec 004",
    "prediccion": "PREDICCIÓN PROPIA (spec 004",
    "reales": "REALES DE PRODUCCIÓN (spec 004",
}

ESCRITURAS_PROHIBIDAS = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+"
    r"(?:generacion|aemet_diario)\b",
    re.IGNORECASE,
)

TOKEN_LITERAL = re.compile(r"ESIOS_TOKEN\s*=\s*[\"'][^\"']+[\"']")


class TestIntegridadNotebook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.codigo = "\n\n".join(
            "".join(celda["source"])
            for celda in cls.notebook["cells"]
            if celda["cell_type"] == "code"
        )

    def test_las_celdas_nuevas_estan_presentes(self):
        for nombre, marcador in MARCADORES.items():
            with self.subTest(celda=nombre):
                self.assertEqual(
                    self.codigo.count(marcador), 1,
                    f"falta o está repetida la celda {nombre!r}",
                )

    def test_las_dos_descargas_siguen_siendo_las_unicas_escritoras(self):
        self.assertEqual(
            self.codigo.count("INSERT OR IGNORE INTO {TABLE_NAME}"), 1)
        self.assertEqual(
            self.codigo.count("INSERT OR IGNORE INTO {AEMET_TABLE}"), 1)

    def test_ninguna_celda_escribe_en_las_tablas_de_observacion(self):
        encontradas = ESCRITURAS_PROHIBIDAS.findall(self.codigo)
        self.assertEqual(
            encontradas, [],
            "hay una escritura directa en generacion/aemet_diario; "
            "la observación no se rellena con previsión (CA-5.1)",
        )

    def test_las_celdas_nuevas_usan_la_capa_de_persistencia(self):
        self.assertIn("prevision_db.save_forecast_rows", self.codigo)
        self.assertIn("prevision_db.save_own_prediction", self.codigo)
        self.assertIn("prevision.resolver_origenes", self.codigo)

    def test_las_dos_capturas_ree_guardan_con_su_fuente(self):
        # El relleno y la captura en vivo escriben siempre como `ree`.
        self.assertEqual(
            self.codigo.count('save_forecast_rows(conn, filas, "ree")'), 2)

    def test_el_relleno_acota_la_ventana_pedida(self):
        # ESIOS devuelve un día más que `end_date`: sin la ventana se archivaría.
        self.assertIn("ventana_solicitada=(inicio, fin)", self.codigo)
        self.assertIn("prevision_db.objetivos_cubiertos", self.codigo)

    def test_el_mapa_usa_la_prevision_de_ree(self):
        self.assertIn("prevision.serie_prevision_generacion", self.codigo)
        self.assertIn("permitir_prev_gen=True", self.codigo)

    def test_el_token_de_esios_se_lee_del_entorno(self):
        self.assertIn('os.getenv("ESIOS_TOKEN")', self.codigo)
        self.assertEqual(
            TOKEN_LITERAL.findall(self.codigo), [],
            "hay un token de ESIOS escrito en el notebook",
        )

    def test_el_archivo_de_fuentes_apunta_a_la_base_de_src(self):
        self.assertIn("prediccion_diaria", self.codigo)


if __name__ == "__main__":
    unittest.main()
