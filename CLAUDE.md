# ENAHO Hub

## Objetivo
Portal interactivo (Streamlit) que vuelve utilizable toda la Encuesta Nacional de Hogares
(ENAHO, 1997-2025) para tesistas e investigadores. Permite explorar los módulos con una
sinopsis de cada uno, buscar cualquier variable en su diccionario (más de 70 mil variables)
y ver en qué módulos y años aparece, graficar al vuelo y descargar las bases listas para
Stata, Python o SPSS. Como diferenciador, un visor muestra el PDF del cuestionario y la
página exacta de la que sale cada variable. Modelo de negocio B2B por cuentas
institucionales (MEF, UP, ULIMA, PUCP). El producto no es la data (es pública): es la capa
que la ordena y el tiempo que ahorra.

## Arquitectura
- Stack: Python, Streamlit y el paquete `inei-microdatos` (trae empaquetado un catálogo y un
  índice de variables offline).
- Principio clave: la metadata (módulos, diccionario, sinopsis, mapeo de páginas) se sirve
  OFFLINE desde archivos pre-horneados en `data/`, sin tocar la red, para que la demo no
  dependa de que INEI esté arriba. Solo la descarga y el graficado de bases usan el portal
  INEI en vivo.
- Capa de datos pre-horneada (corre una vez, offline) en `ai/build_metadata.py`:
  - `data/enaho_modulos.json.gz`: módulos por colección y año, con formatos disponibles y
    enlaces a diccionarios/fichas.
  - `data/enaho_variables.parquet`: tabla larga buscable (variable, etiqueta, modulo,
    modulo_code, coleccion, anio, n_filas).
  - `data/enaho_resumen.json`: conteos globales (colecciones, años, variables únicas, filas,
    fecha del catálogo).
- Sinopsis curadas de módulos en `ai/sinopsis_modulos.py` (función `sinopsis_de`).
- Visor de cuestionario en `ai/build_cuestionarios.py` -> `data/cuestionario_paginas.json`.
- App en `frontend/app.py` con cinco pestañas: Inicio, Explorador de módulos, Diccionario de
  variables, Graficador y Descargas.
- Tres colecciones: "ENAHO Metodología Actualizada (2004+)", "ENAHO Metodología Anterior
  (1997-2003)" y "ENAHO Panel".

## Reglas de Git
- Desarrollo en la branch `initial-development`. NO se toca `main`.
- NO hacer push ni abrir pull requests automáticamente; el autor publica desde GitHub
  Desktop.
- Trabajo posterior a la build inicial: branches `feat/...` y `fix/...` salidas de
  `initial-development`.
- Commits reales, pequeños y coherentes conforme se avanza. No alterar fechas.

## Identidad y estilo de commits
- Autor: Manuel Alfredo Arriola Montenegro (`git user.name`), email
  ma.arriolam@alum.up.edu.pe.
- Mensajes en español, primera persona, concisos. Ej: "Agrego pre-horneado de metadata
  ENAHO", "Construyo pestaña de diccionario de variables".
- SIN firmas ni pies automáticos: nada de "Generated with Claude Code", nada de
  "Co-authored-by: Claude", sin emojis de bot. Solo el mensaje.

## Convenciones de código
- Español en comentarios, UI y docstrings.
- Nunca em dashes. Acentos UTF-8 directos (á é í ó ú ñ), nunca escapes.
- Código conciso, sin preámbulo innecesario. Debe quedar entendible porque se sustenta y
  modifica en vivo ante un evaluador.
