"""
nucleo/habilidades/python/analizador_complejidad.py
Estima complejidad algorítmica por estructura (AST). CONSERVADOR: solo afirma
un Big-O cuando está razonablemente seguro (anidación de for/while reales).
Si hay recursión o estructuras ambiguas, lo dice en vez de inventar un número.
"""
import ast

_MAPA = {0: "O(1)", 1: "O(n)", 2: "O(n²)", 3: "O(n³)"}


def estimar(codigo: str) -> dict:
    try:
        arbol = ast.parse(codigo)
    except SyntaxError:
        return {"big_o": "", "recursiva": False, "detalle": "", "seguro": False}

    prof = _max_anidacion_for_while(arbol)
    recursiva = _hay_recursion(arbol)
    ordena = _usa_orden(arbol)

    # Recursión → no afirmamos O(1)/O(n) por bucles; lo marcamos honesto.
    if recursiva:
        return {"big_o": "recursiva (depende de la recursión)", "recursiva": True,
                "detalle": "es recursiva — la complejidad depende de la profundidad/ramas",
                "seguro": False}

    big_o = _MAPA.get(prof, f"O(n^{prof})")
    if prof <= 1 and ordena:
        big_o = "O(n log n)"

    detalle = []
    if prof >= 2:
        detalle.append(f"{prof} bucles anidados → {big_o}")
    if ordena and prof <= 1:
        detalle.append("dominada por ordenamiento")

    return {"big_o": big_o, "recursiva": False, "detalle": ", ".join(detalle), "seguro": True}


def _max_anidacion_for_while(nodo, prof=0) -> int:
    """Solo cuenta for/while REALES (statements). Las comprehensions cuentan como
    UN nivel (no se recurre a sus generadores internos, que suelen estar acotados).
    Esto evita el falso O(n²) por un all(... for x in par) sobre algo de tamaño fijo."""
    mejor = prof
    for hijo in ast.iter_child_nodes(nodo):
        if isinstance(hijo, (ast.For, ast.While)):
            mejor = max(mejor, _max_anidacion_for_while(hijo, prof + 1))
        elif isinstance(hijo, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            # cuenta como un nivel, pero NO recursar sus generadores internos
            mejor = max(mejor, prof + 1)
        else:
            mejor = max(mejor, _max_anidacion_for_while(hijo, prof))
    return mejor


def _hay_recursion(arbol) -> bool:
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nombre = nodo.name
            for sub in ast.walk(nodo):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == nombre:
                    return True
    return False


def _usa_orden(arbol) -> bool:
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            f = nodo.func
            if isinstance(f, ast.Name) and f.id == "sorted":
                return True
            if isinstance(f, ast.Attribute) and f.attr == "sort":
                return True
    return False