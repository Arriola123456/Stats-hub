"""Sinopsis curadas en español de los módulos estándar de la ENAHO.

`sinopsis_de(nombre_modulo)` resuelve por coincidencia de subcadena sobre el nombre del
módulo (sin distinguir acentos ni mayúsculas). Las reglas van de lo más específico a lo
más genérico para que, por ejemplo, "Servicios a la Vivienda" (gasto) no se confunda con
"Características de la Vivienda y del Hogar".
"""
import unicodedata


def _norm(s):
    """Minúsculas y sin acentos, para comparar de forma robusta."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


# El módulo clave del producto.
_SUMARIA = (
    "Módulo 34 - Sumaria (variables calculadas). Es el módulo clave para investigación: "
    "trae el ingreso y el gasto del hogar ya deflactados y anualizados, las líneas de "
    "pobreza y de pobreza extrema, la condición de pobreza y el factor de expansión. "
    "Variables imprescindibles: inghog1d (ingreso neto del hogar), gashog2d (gasto del "
    "hogar), pobreza (condición de pobreza), mieperho (miembros del hogar), linea y linpe "
    "(líneas de pobreza). Con este módulo se calcula pobreza, desigualdad y bienestar sin "
    "reconstruir nada desde los módulos crudos."
)

_VIVIENDA = (
    "Módulo 100 - Características de la vivienda y del hogar. Tipo y materiales de la "
    "vivienda (paredes, pisos y techos), acceso a agua, desagüe y electricidad, combustible "
    "para cocinar, tenencia y equipamiento básico. Define la unidad de vivienda y alimenta "
    "los indicadores de calidad de vivienda y acceso a servicios (variables p1xx)."
)

_MIEMBROS = (
    "Módulo 200 - Características de los miembros del hogar. Registra a cada persona con "
    "sexo, edad, relación de parentesco con el jefe del hogar, estado civil y lengua "
    "materna. Es el roster que define la composición demográfica del hogar (variables p2xx)."
)

_EDUCACION = (
    "Módulo 300 - Educación. Nivel educativo alcanzado, asistencia y matrícula, atraso "
    "escolar, alfabetismo y gasto en educación. Base de los indicadores de capital humano y "
    "brechas educativas (variables p3xx)."
)

_SALUD = (
    "Módulo 400 - Salud. Percepción de enfermedad, síntoma o accidente, uso de servicios de "
    "salud, afiliación a seguro (SIS, EsSalud) y gasto de bolsillo en consultas, medicinas y "
    "exámenes (variables p4xx)."
)

_EMPLEO = (
    "Módulo 500 - Empleo e ingresos. Condición de actividad (PEA ocupada y desocupada), "
    "ocupación principal y secundaria, rama de actividad, horas trabajadas, categoría y "
    "formalidad, e ingresos laborales y no laborales. Insumo central del ingreso del hogar "
    "(variables p5xx)."
)

def _gasto(nombre):
    """Sinopsis de gasto adaptada al rubro del módulo (para que cada uno sea distinto)."""
    return (f"Gasto del hogar, rubro: {nombre}. Registra el gasto por producto y por forma de "
            "adquisición (compra, autoconsumo, autosuministro o donación). Es insumo del gasto "
            "total del hogar que consolida la Sumaria (módulo 34).")


def _agro(nombre):
    """Sinopsis agropecuaria adaptada al módulo."""
    return (f"Actividad agropecuaria del hogar: {nombre}. Producción, subproductos o gastos de "
            "la actividad agrícola, forestal o pecuaria. Captura ingreso y consumo no monetario, "
            "clave en los hogares rurales.")


_PROGRAMAS = (
    "Módulo de programas sociales. Participación y beneficios de los programas del Estado por "
    "miembro del hogar (Juntos, Pensión 65, Qali Warma, Vaso de Leche, comedores populares, "
    "Beca 18, entre otros). Permite medir cobertura y filtración de la política social."
)

_GOBERNABILIDAD = (
    "Módulo de gobernabilidad, democracia y transparencia. Confianza en las instituciones, "
    "participación ciudadana, percepción de corrupción y opinión sobre la gestión pública. "
    "Es el componente de percepción ciudadana de la ENAHO."
)

_GENERICA = (
    "Módulo de la ENAHO. Consulta el cuestionario y el diccionario de variables para el "
    "detalle de las preguntas que contiene."
)

# (subcadenas normalizadas, texto). Primer match gana; orden de específico a genérico.
_REGLAS = [
    (("sumaria", "variables calculadas"), _SUMARIA),
    (("programas sociales",), _PROGRAMAS),
    (("educacion",), _EDUCACION),
    (("salud",), _SALUD),
    (("empleo", "ingreso"), _EMPLEO),
    (("agricola", "agropecu", "forestal", "pecuari", "subproducto"), _agro),
    (("gobernabilidad", "democracia", "transparencia", "participacion ciudadana"), _GOBERNABILIDAD),
    (("alimentos", "vestido", "calzado", "transporte", "comunicaciones", "muebles",
      "enseres", "esparcimiento", "diversion", "cultura", "equipamiento", "mantenimiento",
      "servicios a la vivienda", "otros bienes", "transferencias", "instituciones benefica"), _gasto),
    (("miembros",), _MIEMBROS),
    (("vivienda", "hogar"), _VIVIENDA),
]


def sinopsis_de(nombre_modulo):
    """Devuelve la sinopsis en español del módulo. Algunas reglas (gasto, agro) adaptan el
    texto al nombre del módulo para que cada uno sea distinto."""
    n = _norm(nombre_modulo)
    if not n:
        return _GENERICA
    for claves, texto in _REGLAS:
        if any(k in n for k in claves):
            return texto(nombre_modulo) if callable(texto) else texto
    return _GENERICA


if __name__ == "__main__":
    # Prueba de cobertura sobre los nombres reales de los módulos 2024.
    ejemplos = [
        "Sumarias ( Variables Calculadas )",
        "Características de la Vivienda y del Hogar",
        "Características de los Miembros del Hogar",
        "Educación", "Salud", "Empleo e Ingresos",
        "Gastos en Alimentos y Bebidas (Módulo 601)",
        "Servicios a la Vivienda", "Equipamiento del Hogar",
        "Programas Sociales  (Miembros del Hogar)",
        "Producción Agrícola", "Gobernabilidad, Democracia y Transparencia",
    ]
    for nombre in ejemplos:
        tag = "GENERICA" if sinopsis_de(nombre) is _GENERICA else "ok"
        print(f"  [{tag}] {nombre}")
