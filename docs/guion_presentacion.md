# Guion de presentación — Stats (7 min + 3 min Q&A)

Hook que se repite: **"Somos el Bloomberg de los datos públicos del Perú."**

## 1. Pitch de 7 minutos (timing por bloque)

| Tiempo | Slides | Qué decir (ideas clave) |
|---|---|---|
| **0:00-0:40** | 1-2 | Apertura fuerte. "Bloomberg tomó data financiera pública y la volvió utilizable al instante; construyó un imperio. La data pública del Perú es igual de valiosa y está igual de desordenada. **Stats** la vuelve utilizable. Empezamos por la ENAHO." |
| **0:40-1:40** | 4-5 | **Problema + insight.** La ENAHO es la fuente clave de pobreza/empleo/ingresos, pero llega en decenas de módulos, +70 mil variables, 30 años. Encontrar una variable toma horas. "El valor no es la data (es pública): es la capa que la ordena", como Bloomberg con los precios. |
| **1:40-5:00** | 6-8 + **DEMO** | **Solución + demo EN VIVO** (lo más importante). Muestra la app (ver bloque 2). Cierra con la arquitectura offline-first (slide 8): "todo pre-horneado, no depende de que INEI esté arriba". |
| **5:00-6:00** | 10-12 | **Mercado + modelo.** 97 universidades, ~1.2 M de estudiantes (SUNEDU); miles de tesis/año. Suscripción como Bloomberg: B2B + freemium, **margen >90%** (software sobre data pública). Moat: el mapeo variable->página es un dataset propio. |
| **6:00-7:00** | 14-16 | **Tracción + visión + ask.** MVP vivo y desplegado. Roadmap: toda la ENAHO -> ENDES/CENAGRO -> todo dato público. **Visión LATAM**: cada país tiene su encuesta (CASEN, ENIGH, GEIH, EPH...). Cierra: "el Bloomberg de los datos públicos de Latinoamérica" + el ask (S/. 50k pre-seed, primeras 10 cuentas pagas). |

Slides que en el pitch se pasan rápido (no leer entero): 3 (founder, una línea), 9 (por qué ahora, 15s), 13 (GTM, 15s).

## 2. Demo en vivo paso a paso (3-4 min, el momento clave)

Ten la URL desplegada abierta. **Plan B: el video de respaldo** por si falla internet.

1. **Abre la app.** Señala el logo y di "Stats, en vivo, desplegado".
2. **Pestaña Diccionario** (el diferenciador):
   - Colección *ENAHO Metodología Actualizada* -> Módulo *Modulo03 · Educación*.
   - Elige una variable con el icono **📄** (ej. `p301a`).
   - A la derecha aparece la **página exacta del cuestionario con la pregunta resaltada** en naranja. Di: *"Esto es lo que nadie más tiene: de un código de variable a la pregunta exacta del PDF."*
   - Cambia a *Modulo05 · Empleo* y otra variable para mostrar que es general.
3. **Pestaña Indicadores ENAHO 2024**:
   - Indicador *Tasa de pobreza (%)* -> desglose *Por departamento*.
   - Cambia el **color**, activa **barras horizontales**, descarga **PNG** y **Excel**.
   - Di: *"Datos reales de 2024, ponderados con el factor de expansión, sin tocar la red. Pobreza nacional 27.6% — coincide con la cifra oficial de INEI."*
4. (Si sobra tiempo) **Explorador** o **Descargas** en 10 segundos.
5. Vuelve al deck para mercado/ask.

## 3. Preguntas probables del jurado (Q&A) y respuestas

- **"¿Por qué no usar directamente el portal de INEI?"** El portal es crudo: sin búsqueda de variables, sin sinopsis ni visor de cuestionario; descubrir una variable toma horas. Stats es la **capa de descubrimiento**.
- **"Si la data es pública, ¿cuál es el negocio?"** No vendo la data (gratis): vendo el **tiempo ahorrado y el acceso**, como Bloomberg con precios públicos. Suscripción B2B + freemium.
- **"¿Cuál es el moat si copian la app?"** El **dataset propio variable->página** del cuestionario (document AI curado), la capa de metadata, la marca/comunidad y la velocidad de ejecución.
- **"¿El tamaño de mercado es real?"** 97 universidades licenciadas, ~1.2 M de estudiantes (SUNEDU); miles de tesis/año en economía y ciencias sociales; sector público (MEF, ministerios).
- **"¿Cómo escala a LATAM?"** Mismo pipeline; cada país tiene su encuesta nacional de hogares (CASEN en Chile, ENIGH en México, GEIH en Colombia, EPH en Argentina...).
- **"¿La data es correcta?"** Sí: pobreza nacional **27.6%** coincide con la cifra oficial de INEI 2024; ponderada con el factor de expansión (`factor07 * mieperho`).
- **"¿Qué hizo la IA y qué hiciste tú?"** (honestidad) Claude Code escribió el código bajo mi dirección; yo definí objetivo, arquitectura offline-first, alcance, negocio y validé cada fase. Puedo explicar y modificar cualquier parte.
- **"¿Por qué ENAHO primero?"** Es la encuesta más usada (pobreza, empleo, ingresos), la joya de la corona, y tengo founder-market fit (la sufro en mis tesis).

## 4. Tour del código (para explicar o modificar en vivo)

La rúbrica avisa: pueden pedirte **explicar y modificar el repo en vivo**. Ten esto claro.

**Estructura:**
- `ai/` — scripts de horneado (corren una vez, offline). `frontend/app.py` — la app (5 pestañas). `data/` — la capa offline pre-horneada (versionada).
- `ai/build_metadata.py` -> diccionario y módulos. `ai/build_cuestionarios.py` -> mapeo variable->página (document AI). `ai/build_indicadores.py` -> indicadores ponderados. `ai/comun.py` -> helpers.

**Si te piden modificar algo, aquí está:**
- **"Agrega un indicador"** -> `ai/build_indicadores.py`, en el dict `indicadores` (copia una entrada y define la función ponderada, p. ej. ingreso per cápita = `media_hogar` dividida por miembros). Re-hornear con `python ai/build_indicadores.py`.
- **"Cambia el gráfico (color/orientación)"** -> `frontend/app.py`, `tab_indicadores` y `_figura_indicador` (matplotlib).
- **"Agrega un módulo o año al visor"** -> `ai/build_cuestionarios.py`: constantes `MODULOS_MVP` y `ANIOS`.
- **"¿Cómo mapeas variable->página?"** -> `ai/build_cuestionarios.py`: `construir_anclas` (anclas monótonas número->página, limpiando outliers con subsecuencia no decreciente) + `ubicar` (interpola la página). El resaltado se hace en `frontend/app.py` `_pagina_con_pregunta` con pymupdf.
- **"¿Cómo ponderas la pobreza?"** -> `ai/build_indicadores.py`, `tasa_pobreza`: peso poblacional `w_pers = factor07 * mieperho`.

**Mensaje clave:** la decisión de arquitectura es **offline-first** (capa de metadata pre-horneada en `data/`), por eso la demo no depende de INEI y es instantánea. Solo Descargas toca el portal en vivo.
