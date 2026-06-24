# ENAHO Hub

Portal interactivo que vuelve utilizable toda la Encuesta Nacional de Hogares (ENAHO) para
tesistas e investigadores: explora módulos, busca entre más de 70 mil variables, consulta
indicadores clave y descarga bases listas para Stata, Python o SPSS, con el cuestionario
abierto en la página exacta de cada variable.

## Problema
La ENAHO es la principal fuente de pobreza, empleo e ingresos del Perú, pero llega repartida
en decenas de módulos, tres metodologías, varios formatos y casi 30 años, con codificación
incómoda y más de 70 mil variables. Encontrar una variable, saber en qué módulo y año está y
bajar la base correcta toma horas. Y el portal de INEI a veces no responde.

## Solución
ENAHO Hub ordena esa data pública y la sirve desde una capa de metadata pre-horneada que
funciona OFFLINE:
- Explorador de módulos con una sinopsis curada de cada uno.
- Diccionario de variables buscable (por nombre o etiqueta) que muestra en qué módulos y
  años aparece cada variable.
- Visor de cuestionario: al elegir una variable se muestra el PDF del cuestionario en la
  página exacta de la pregunta (el diferenciador).
- Indicadores ENAHO 2024 (pobreza, pobreza extrema, ingreso y gasto del hogar) calculados
  desde la Sumaria con el factor de expansión y servidos offline.
- Descargas que bajan la base de INEI en vivo (cacheada) y la entregan lista para Stata,
  SPSS, Python o CSV.
- "Modo institución" que demuestra el esquema de negocio B2B por cuentas (MEF, UP, ULIMA,
  PUCP), sin login real.

El producto no es la data (es pública): es la capa que la ordena y el tiempo que ahorra.

## Demo (alcance actual)
Esta primera versión es una demo acotada a **ENAHO 2024** para validar el flujo completo de
punta a punta. El mecanismo está parametrizado por año (constante `ANIOS` en los scripts de
`ai/`) y generaliza al resto de años con solo ampliarla y volver a hornear.

## Cómo correr
```bash
pip install -r requirements.txt

# 1. Hornear la metadata offline (genera data/enaho_*.*). No toca la red.
python ai/build_metadata.py

# 2. (Opcional) Mapear variables a la página de su cuestionario. Descarga PDFs de INEI.
python ai/build_cuestionarios.py

# 3. (Opcional) Hornear los indicadores. Descarga la Sumaria una vez.
python ai/build_indicadores.py

# 4. (Opcional) Activar el modo institución copiando el ejemplo de secrets.
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# 5. Levantar la app.
streamlit run frontend/app.py
```
Con los pasos 1 y 3 la app es totalmente funcional offline. Solo las descargas (y los pasos 2
y 3 de horneado) tocan INEI en vivo.

## Arquitectura
Principio: la metadata y los indicadores se sirven OFFLINE desde archivos pre-horneados en
`data/`, sin red, para que la demo no dependa de que INEI esté arriba. Solo las descargas
usan el portal en vivo.

- `ai/build_metadata.py` lee el catálogo y el índice de variables empaquetados en
  `inei-microdatos` y hornea `data/enaho_modulos.json.gz`, `data/enaho_variables.parquet` y
  `data/enaho_resumen.json`.
- `ai/sinopsis_modulos.py` resuelve la sinopsis de cada módulo por subcadena de su nombre.
- `ai/build_cuestionarios.py` descarga los cuestionarios, extrae texto por página
  (pdfplumber; pymupdf de respaldo; PaddleOCR opcional para escaneados) y mapea cada variable
  a su página por el número de pregunta, generando `data/cuestionario_paginas.json`.
- `ai/build_indicadores.py` descarga la Sumaria una vez y calcula indicadores ponderados
  (pobreza, ingreso, gasto) por dominio y área, generando `data/indicadores.json`.
- `frontend/app.py` es la app Streamlit con cinco pestañas (Inicio, Explorador, Diccionario,
  Indicadores, Descargas).

Tres colecciones: "ENAHO Metodología Actualizada (2004+)", "ENAHO Metodología Anterior
(1997-2003)" y "ENAHO Panel".

## Estructura de carpetas
```
ai/
  build_metadata.py       hornea la metadata offline
  sinopsis_modulos.py     sinopsis curadas por módulo
  build_cuestionarios.py  mapea variable -> página del cuestionario
  build_indicadores.py    hornea indicadores de pobreza e ingreso (Sumaria)
  comun.py                helpers (codificación, colección, módulo)
frontend/app.py           app Streamlit (5 pestañas)
data/                     metadata pre-horneada (versionada); PDFs/ZIPs fuera de git
.streamlit/               secrets.toml.example (modo institución)
.github/workflows/ci.yml  lint y parse básicos
CLAUDE.md                 objetivo, arquitectura y convenciones del proyecto
```

## Partes asistidas por agentes de IA
El curso exige declarar el uso de IA, así que lo detallo. La construcción de este repositorio
fue asistida por un agente de IA (Claude Code) trabajando bajo mi dirección y revisión. En
concreto, la IA ayudó a implementar:
- Los scripts de `ai/` (`build_metadata.py`, `sinopsis_modulos.py`, `build_cuestionarios.py`,
  `build_indicadores.py`, `comun.py`).
- La app `frontend/app.py` (cinco pestañas, caché, modo institución, visor de cuestionario,
  indicadores pre-horneados).
- La heurística de mapeo variable -> página del cuestionario (búsqueda del número de pregunta
  por regex con verificación de contexto).
- La documentación (`CLAUDE.md`, este README) y la configuración de CI.

Yo definí el objetivo, la arquitectura offline-first, el alcance (demo ENAHO 2024) y las
decisiones de diseño, y revisé y validé cada fase. Los datos provienen de INEI (ENAHO) a
través del paquete `inei-microdatos`.

## Licencia
MIT, Manuel Alfredo Arriola Montenegro. Ver `LICENSE`.
