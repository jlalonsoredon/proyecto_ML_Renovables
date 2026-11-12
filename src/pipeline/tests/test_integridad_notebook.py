"""Integridad de las tablas de observación (spec 004, RF-5; spec 005, CA-5.4).

Comprobación estática del notebook: las únicas funciones que escriben en
`generacion` y `aemet_diario` son las dos descargas que ya existían. Las celdas
nuevas de la spec 004 escriben solo en las tablas del archivo de previsiones y de
la predicción propia; la celda de la spec 005 lee el archivo en solo lectura y
añade la columna `eolica_prev` sin tocar la observación.

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
    "prevision_objetivo": "PREVISIÓN DEL DÍA OBJETIVO (spec 005",
    "eda_variable": "EDA DE LA VARIABLE NUEVA (spec 006",
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

    # ── Spec 005: previsión del día objetivo ─────────────────────────────────
    def test_la_celda_de_la_prevision_del_objetivo_usa_la_logica_pura(self):
        for llamada in (
            "prevision.serie_prevision_objetivo(",
            "prevision.serie_prevision_rellenada(",
            "prevision.resumen_prevision(",
            "prevision.rellenar_prevision(",
        ):
            with self.subTest(llamada=llamada):
                self.assertIn(llamada, self.codigo)

    def test_la_celda_del_objetivo_recarga_prevision_antes_de_usarla(self):
        celda = next(
            celda for celda in self.notebook["cells"]
            if celda["cell_type"] == "code"
            and MARCADORES["prevision_objetivo"] in "".join(celda["source"])
        )
        codigo = "".join(celda["source"])
        self.assertIn("importlib.reload(prevision)", codigo)
        self.assertLess(
            codigo.index("importlib.reload(prevision)"),
            codigo.index("prevision.serie_prevision_objetivo("),
        )

    def test_la_prevision_del_objetivo_llega_al_mapa(self):
        self.assertIn("prevision_objetivo=", self.codigo)
        self.assertIn('"eolica_prev"', self.codigo)

    def test_el_archivo_de_previsiones_se_abre_en_solo_lectura(self):
        # La celda nueva no puede escribir en la base de observación.
        self.assertGreaterEqual(
            self.codigo.count("?mode=ro"), 2,
            "falta la apertura en solo lectura del archivo de previsiones",
        )

    def test_el_notebook_escribe_el_acta_de_la_prevision(self):
        self.assertIn("prevision_ree_como_feature.json", self.codigo)
        self.assertIn("prevision.informe_prevision_ree(", self.codigo)

    # ── Spec 006: EDA de la variable nueva y familia del modelo ───────────────
    def test_la_celda_eda_usa_la_correlacion_pura(self):
        celda = next(
            celda for celda in self.notebook["cells"]
            if celda["cell_type"] == "code"
            and MARCADORES["eda_variable"] in "".join(celda["source"])
        )
        codigo = "".join(celda["source"])
        self.assertIn("exploracion.correlacion_pearson(", codigo)

    def test_el_eda_ree_va_despues_del_solar_en_feature_engineering(self):
        celdas = self.notebook["cells"]
        posicion_feature_engineering = next(
            indice for indice, celda in enumerate(celdas)
            if celda["cell_type"] == "markdown"
            and "### FEATURE ENGINEERING" in "".join(celda["source"])
        )
        posicion_solar = next(
            indice for indice, celda in enumerate(celdas)
            if celda["cell_type"] == "markdown"
            and "Evaluamos la relación de las variables solares" in "".join(celda["source"])
        )
        posicion_eda_ree = next(
            indice for indice, celda in enumerate(celdas)
            if celda["cell_type"] == "code"
            and MARCADORES["eda_variable"] in "".join(celda["source"])
        )
        posicion_bloque_prevision = next(
            indice for indice, celda in enumerate(celdas)
            if celda["cell_type"] == "markdown"
            and "### BLOQUE DE PREVISIÓN (spec 003)" in "".join(celda["source"])
        )
        self.assertLess(posicion_feature_engineering, posicion_solar)
        self.assertLess(posicion_solar, posicion_eda_ree)
        self.assertLess(
            posicion_eda_ree, posicion_bloque_prevision,
            "el EDA de REE debe quedar dentro de FEATURE ENGINEERING, después del solar",
        )

        codigo_eda = "".join(celdas[posicion_eda_ree]["source"])
        for grafica in ("plt.plot(", "plt.scatter(", "sns.heatmap(",
                        "exploracion.correlacion_pearson("):
            with self.subTest(grafica=grafica):
                self.assertIn(grafica, codigo_eda)

    def test_el_split_declara_y_valida_las_columnas_finales(self):
        celda_split = next(
            celda for celda in self.notebook["cells"]
            if celda["cell_type"] == "code"
            and "# Split 80/20 temporal" in "".join(celda["source"])
        )
        codigo = "".join(celda_split["source"])
        self.assertIn("usa df_ml, COLUMNAS_MODELO y TARGET", codigo)
        self.assertNotIn("usa df_ml, FEATURE_COLS y TARGET", codigo)
        self.assertIn("train[COLUMNAS_MODELO]", codigo)
        self.assertIn("test[COLUMNAS_MODELO]", codigo)
        self.assertIn("X_train.shape[1] == len(COLUMNAS_MODELO)", codigo)
        self.assertIn("X_test.shape[1] == len(COLUMNAS_MODELO)", codigo)
        self.assertIn("Features finales del modelo", codigo)

    def test_las_salidas_del_split_y_ranking_muestran_19_features(self):
        celdas = self.notebook["cells"]
        split = next(
            celda for celda in celdas
            if celda["cell_type"] == "code"
            and "# Split 80/20 temporal" in "".join(celda["source"])
        )
        ranking = next(
            celda for celda in celdas
            if celda["cell_type"] == "code"
            and "Entrenamiento del ranking con" in "".join(celda["source"])
        )

        def texto_salida(celda):
            partes = []
            for salida in celda.get("outputs", []):
                partes.extend(salida.get("text", []))
                for representacion in salida.get("data", {}).values():
                    if isinstance(representacion, list):
                        partes.extend(representacion)
                    elif isinstance(representacion, str):
                        partes.append(representacion)
            return "".join(partes)

        self.assertIn("Features finales del modelo (19)", texto_salida(split))
        self.assertIn("Entrenamiento del ranking con 19 features", texto_salida(ranking))

    def test_el_eda_ree_guarda_las_tres_graficas_en_el_notebook(self):
        eda = next(
            celda for celda in self.notebook["cells"]
            if celda["cell_type"] == "code"
            and MARCADORES["eda_variable"] in "".join(celda["source"])
        )
        imagenes = sum(
            "image/png" in salida.get("data", {})
            for salida in eda.get("outputs", [])
        )
        self.assertGreaterEqual(imagenes, 3)

    def test_las_salidas_del_notebook_no_exponen_claves_de_api(self):
        salidas = json.dumps(
            [celda.get("outputs", []) for celda in self.notebook["cells"]],
            ensure_ascii=False,
        )
        self.assertNotRegex(
            salidas,
            r"(?i)(?:api_key|esios_token)=([^&\s\"']{16,})",
        )

    def test_feature_engineering_no_afirma_que_produccion_sigue_en_16(self):
        celdas = self.notebook["cells"]
        inicio = next(
            indice for indice, celda in enumerate(celdas)
            if celda["cell_type"] == "markdown"
            and "### FEATURE ENGINEERING" in "".join(celda["source"])
        )
        fin = next(
            indice for indice in range(inicio + 1, len(celdas))
            if celdas[indice]["cell_type"] == "markdown"
            and "### BLOQUE DE PREVISIÓN (spec 003)" in "".join(celdas[indice]["source"])
        )
        bloque = "\n".join(
            "".join(celda["source"]) for celda in celdas[inicio:fin]
        )
        self.assertNotIn("El modelo de producción sigue con las 16 variables", bloque)

    def test_las_16_features_se_etiquetan_como_base_no_como_train_final(self):
        celdas = self.notebook["cells"]
        feature_engineering = next(
            celda for celda in celdas
            if celda["cell_type"] == "code"
            and "df_ml = df_eolica.reset_index()" in "".join(celda["source"])
        )
        codigo = "".join(feature_engineering["source"])
        self.assertIn("Dataset base antes de eolica_prev", codigo)
        self.assertIn("el vector final del modelo", codigo)
        self.assertNotIn("Modelo de producción intacto:", self.codigo)

        salidas = json.dumps(
            [celda.get("outputs", []) for celda in celdas],
            ensure_ascii=False,
        )
        self.assertIn("Dataset base antes de eolica_prev", salidas)
        self.assertNotIn("Modelo de producción intacto:", salidas)

    def test_el_ranking_entrena_con_las_columnas_adoptadas(self):
        self.assertIn("train[COLUMNAS_MODELO]", self.codigo)
        self.assertIn("test[COLUMNAS_MODELO]", self.codigo)
        self.assertNotIn("X_train, y_train = train[FEATURE_COLS]", self.codigo)

    def test_el_walk_forward_de_variables_va_antes_del_split(self):
        posicion_walk = self.codigo.index("folds = evaluacion.walk_forward_folds")
        posicion_split = self.codigo.index("SPLIT_IDX = int(len(df_ml)")
        self.assertLess(
            posicion_walk, posicion_split,
            "el walk-forward debe decidir las columnas antes del split",
        )

    def test_el_notebook_elige_y_declara_la_familia(self):
        for marca in (
            "decision_familia = evaluacion.criterio_aceptacion(",
            "FAMILIA_MODELO =",
            "def predecir_produccion(",
            '"familia": FAMILIA_MODELO',
            "familia_como_modelo.json",
        ):
            with self.subTest(marca=marca):
                self.assertIn(marca, self.codigo)

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
