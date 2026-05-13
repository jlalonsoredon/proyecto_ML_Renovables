# Proyecto ML — Predicción de Generación Eólica Peninsular

## Descripción

Este proyecto construye un modelo de Machine Learning capaz de predecir la generación diaria de energía eólica en la España peninsular, combinando datos históricos de producción de la Red Eléctrica de España (REE) con datos meteorológicos de la Agencia Estatal de Meteorología (AEMET).

El sistema incluye también un backend FastAPI que sirve el modelo entrenado como una API REST, permitiendo obtener predicciones para el día siguiente en tiempo real.

---

## Estructura del Proyecto

```
Proyecto-ML/
├── api.ipynb               # Notebook principal: EDA, Feature Engineering y entrenamiento
├── ree_generacion.db       # Base de datos SQLite con datos de REE y AEMET
├── backend/                # API REST con FastAPI
│   ├── requirements.txt    # Dependencias del backend
│   └── ...
├── frontend/               # Interfaz web de visualización
├── modelos/
│   └── lr_eolica.joblib    # Modelo entrenado serializado (Linear Regression + scaler)
└── .env                    # Claves de API (AEMET_API_KEY)
```

---

## Flujo del Notebook (`api.ipynb`)

### 1. Adquisición de datos — REE

Se descarga la estructura de generación eléctrica diaria desde la API pública de REE (`apidatos.ree.es`) desde enero de 2022 hasta la fecha actual.

- **Tecnologías capturadas:** Eólica, Solar fotovoltaica, Solar térmica, Hidráulica, Hidroeólica, otras renovables y no renovables.
- Los datos se almacenan en una tabla SQLite (`generacion`) con clave primaria `(datetime, tecnologia)` para evitar duplicados.
- La descarga se realiza en tramos de 30 días para evitar timeouts.

### 2. Adquisición de datos — AEMET

Se descargan datos climáticos diarios de estaciones meteorológicas próximas a los principales parques de generación renovable de España:

| Tipo | Parques / Zonas | Variables descargadas |
|------|-----------------|----------------------|
| Eólica | Andevalo (Huelva), Gecama (Cuenca), Maranchón (Guadalajara), Borja (Zaragoza), Tarifa (Cádiz), Briviesca (Burgos), La Muela (Zaragoza) | `velmedia`, `racha` |
| Fotovoltaica | Francisco Pizarro y Núñez de Balboa (Badajoz), Mula (Murcia), Don Rodrigo (Sevilla), Chiprana (Zaragoza) | `tmed`, `tmin`, `tmax`, `sol` |
| Hidráulica | La Muela (Valencia), Aldeadávila (Salamanca), Brozas (Cáceres) | `prec` |

Los datos se almacenan en la tabla `aemet_diario` con clave primaria `(fecha, indicativo)`.

### 3. Análisis de calidad y decisión de alcance

Se realizó un diagnóstico de nulos y cobertura temporal por estación:

- **Solar fotovoltaica descartada:** 3 de 5 estaciones no tienen datos de insolación (`sol`), y otra supera el 50% de nulos. Sin insolación no es viable predecir generación fotovoltaica.
- **Hidráulica descartada:** los datos de precipitación local no representan el caudal real, que depende de toda la cuenca hidrográfica.
- ✅ **Se selecciona la energía eólica** como objetivo del modelo, ya que las 6 estaciones disponen de datos de velocidad media y racha con buena cobertura.

### 4. Preprocesamiento y relleno de valores nulos

Se evaluaron seis métodos de interpolación mediante validación hold-out (enmascarando el 15% de los valores conocidos):

| Método | Descripción |
|--------|-------------|
| Forward Fill | Propaga el último valor conocido |
| Backward Fill | Propaga el siguiente valor conocido |
| **Linear Interpolation** ✅ | **Mejor resultado global** |
| Cubic Interpolation | Interpolación cúbica |
| KNN Mean (n=8) | Media de los 8 vecinos más próximos |
| Seasonal Mean | Media estacional (ventana anual) |

**Conclusión:** La **interpolación lineal** obtuvo el menor RMSE en la mayoría de estaciones y fue seleccionada para rellenar los huecos en `velmedia` y `racha`.

Tras interpolar, se calculó la **media diaria** de todas las estaciones eólicas, generando un único valor representativo nacional para cada día.

### 5. Feature Engineering

El dataset final de entrada al modelo incluye las siguientes características construidas sobre `df_eolica`:

| Feature | Descripción |
|---------|-------------|
| `velmedia` | Velocidad media del viento (m/s) |
| `racha` | Racha máxima del viento (m/s) |
| `mes` | Mes del año (1–12) — estacionalidad |
| `dia_semana` | Día de la semana (0–6) |
| `dia_año` | Día del año (1–365) |
| `eolica_lag1/2/3/7` | Generación eólica de los días anteriores |
| `vel_ma3/7/14` | Media móvil de velocidad (3, 7 y 14 días) |
| `racha_ma3/7/14` | Media móvil de racha (3, 7 y 14 días) |
| `eolica_ma7` | Media móvil del target con shift (sin data leakage) |

### 6. Entrenamiento y evaluación de modelos

División temporal **80 % train / 20 % test** (sin mezcla aleatoria, respetando el orden cronológico).

Se entrenaron los siguientes modelos:

| Modelo | Notas |
|--------|-------|
| Linear Regression | Con StandardScaler |
| Ridge (α=10) | Regularización L2 |
| Lasso (α=0.1) | Regularización L1 |
| Random Forest | 300 estimadores, max_depth=12 |
| XGBoost | 400 estimadores, lr=0.05 |
| LightGBM | 400 estimadores, lr=0.05 |
| Red Neuronal (MLP) | Capas (128, 64, 32), early stopping |
| SARIMAX(1,0,1)(1,1,1,7) | Serie temporal con exógenas velmedia + racha |

**Métricas de evaluación:** RMSE (MWh), MAE (MWh), R², MAPE (%), Accuracy% (quintiles).

### 7. Pronóstico para el día siguiente

Se consulta la API de predicción de AEMET (`/prediccion/especifica/municipio/diaria/{municipio}`) para los 7 municipios asociados a las estaciones eólicas y se construye el vector de features en tiempo real para predecir la generación del día siguiente con todos los modelos entrenados.

### 8. Serialización del modelo

El modelo seleccionado (**Linear Regression**) junto con su scaler y la lista de features se serializa con `joblib` en `modelos/lr_eolica.joblib` para ser consumido por el backend FastAPI.

---

## Conclusiones

1. **Foco en eólica:** La falta de datos fiables de insolación en las estaciones cercanas a plantas fotovoltaicas, y la baja correlación entre precipitación local y generación hidráulica, llevaron a centrar el proyecto exclusivamente en la predicción de generación eólica.

2. **Interpolación lineal:** Es el método más robusto para rellenar los huecos temporales de las variables de viento, con menor RMSE frente a métodos más complejos como la interpolación cúbica o la media estacional.

3. **Correlación viento–eólica:** Se observa una correlación clara y consistente entre la velocidad media del viento (y la racha) y la generación eólica nacional, visible tanto en series temporales como en el heatmap de correlaciones.

4. **Modelo seleccionado:** Linear Regression ofrece un buen equilibrio entre interpretabilidad y rendimiento predictivo, siendo seleccionado como modelo de producción. Los modelos de boosting (XGBoost, LightGBM) y el SARIMAX también ofrecen resultados competitivos.

5. **Predicción en tiempo real:** Gracias a la API de predicción de AEMET es posible obtener pronósticos meteorológicos para el día siguiente y traducirlos directamente en una predicción de generación eólica, cerrando así el ciclo completo desde los datos hasta la predicción.

---

## Tecnologías utilizadas

- **Python 3.x**
- `pandas`, `numpy`, `scipy` — manipulación y análisis de datos
- `scikit-learn` — preprocesamiento, modelos clásicos y red neuronal MLP
- `xgboost`, `lightgbm` — gradient boosting
- `statsmodels` — SARIMAX
- `matplotlib`, `seaborn` — visualización
- `requests`, `python-dotenv` — consumo de APIs REST
- `sqlite3` — almacenamiento local de datos
- `joblib` — serialización del modelo
- `FastAPI`, `uvicorn` — backend de la API REST

---

## Configuración

1. Crea un archivo `.env` en la raíz del proyecto con tu clave de AEMET:

```env
AEMET_API_KEY=tu_clave_aqui
```

2. Instala las dependencias del backend:

```bash
pip install -r backend/requirements.txt
```

3. Ejecuta el notebook `api.ipynb` de principio a fin para descargar datos, entrenar el modelo y guardarlo en `modelos/`.

4. Lanza el backend:

```bash
cd backend
uvicorn main:app --reload
```
