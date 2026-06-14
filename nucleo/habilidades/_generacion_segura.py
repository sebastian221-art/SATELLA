"""
nucleo/habilidades/_generacion_segura.py
Generación de código A PRUEBA DE CORTES. Si el modelo corta la respuesta por el
tope de tokens, detecta que quedó incompleta y le pide que CONTINÚE desde donde
quedó, hasta completarla. Compartido por copia, creador y la habilidad de código.

No es una skill (archivo suelto, el registro ignora archivos, no carpetas).
"""
import ast
import re
from nucleo.habilidades.python import _llm


def limpiar_fences(txt):
    if not txt:
        return ""
    t = txt.strip()
    m = re.search(r"```(?:\w+)?\s*(.*?)```", t, re.S)
    return m.group(1).strip() if m else t


def _brackets_desbalanceados(codigo):
    pares = {")": "(", "]": "[", "}": "{"}
    pila, en_str = [], None
    for ch in codigo:
        if en_str:
            if ch == en_str:
                en_str = None
            continue
        if ch in ("'", '"'):
            en_str = ch
        elif ch in "([{":
            pila.append(ch)
        elif ch in ")]}":
            if not pila or pila[-1] != pares[ch]:
                return True
            pila.pop()
    return len(pila) > 0


def esta_completo(codigo):
    """True si el código parece terminado; False si quedó cortado a mitad."""
    if not codigo or not codigo.strip():
        return False
    try:
        ast.parse(codigo)
        return True  # parsea => completo
    except SyntaxError:
        pass
    if _brackets_desbalanceados(codigo):
        return False  # paréntesis/llaves abiertos => cortado
    ult = (codigo.rstrip().splitlines() or [""])[-1].rstrip()
    if ult.endswith((",", "=", "+", "-", "(", "[", "{", "\\", ":", "->", " and", " or")):
        return False  # termina a mitad de expresión => cortado
    return True  # roto pero balanceado: no es corte, no seguir pidiendo


def completar_texto(prompt, system, max_tokens=2000, max_cont=4, temperature=0.3):
    """Genera TEXTO largo (prosa/markdown/tablas) a prueba de cortes.
    Usa finish_reason='length' de Groq para detectar el corte y continúa hasta terminar.
    Es el equivalente de completar_codigo pero para texto (no chequea sintaxis)."""
    if not _llm.disponible():
        return ""
    texto, truncado = _llm.chat_meta(prompt, max_tokens=max_tokens, temperature=temperature, system=system)
    conts = 0
    while texto and truncado and conts < max_cont:
        conts += 1
        cola = texto[-400:]
        prompt_cont = (
            "Tu respuesta quedó CORTADA por el límite de tokens. Continuá EXACTAMENTE desde "
            "donde quedó, SIN repetir lo ya escrito y sin reintroducir el tema, solo el resto. "
            "Esto es lo último que alcanzaste a escribir:\n\n" + cola
        )
        resto, truncado = _llm.chat_meta(prompt_cont, max_tokens=max_tokens, temperature=temperature, system=system)
        if not resto:
            break
        texto = texto.rstrip() + " " + resto.lstrip()
    return texto


def completar_codigo(prompt, system, max_tokens=4000, max_cont=4):
    """Genera código y, si se corta, pide continuaciones hasta completarlo.
    Usa finish_reason='length' (señal real de corte de Groq) + chequeo de sintaxis."""
    if not _llm.disponible():
        return ""
    bruto, truncado = _llm.chat_meta(prompt, max_tokens=max_tokens, temperature=0.2, system=system)
    codigo = limpiar_fences(bruto)
    conts = 0
    while codigo and (truncado or not esta_completo(codigo)) and conts < max_cont:
        conts += 1
        cola = "\n".join(codigo.splitlines()[-25:])
        prompt_cont = (
            "Este código quedó CORTADO por el límite de tokens. Continualo EXACTAMENTE "
            "desde donde quedó, SIN repetir lo ya escrito, sin explicaciones, solo el resto "
            "del código:\n\n" + cola
        )
        resto, truncado = _llm.chat_meta(prompt_cont, max_tokens=max_tokens, temperature=0.1, system=system)
        resto = limpiar_fences(resto)
        if not resto:
            break
        codigo = codigo.rstrip("\n") + "\n" + resto
    return codigo


def generar_varios(planificador_prompt, system_plan, generador_de_archivo, system_gen):
    """
    Para trabajos GRANDES de varios archivos: 1) pide un plan (lista de archivos),
    2) genera cada uno completo (anti-corte), 3) devuelve [{archivo, codigo}].
    `generador_de_archivo(nombre, descripcion)` arma el prompt de cada archivo.
    """
    if not _llm.disponible():
        return []
    plan_txt = _llm.chat(planificador_prompt, max_tokens=600, temperature=0.2, system=system_plan)
    archivos = re.findall(r"[-*\d.]\s*([\w/]+\.\w+)\s*[:\-]\s*(.+)", plan_txt or "")
    salida = []
    for nombre, desc in archivos[:8]:
        prompt = generador_de_archivo(nombre.strip(), desc.strip())
        codigo = completar_codigo(prompt, system_gen)
        salida.append({"archivo": nombre.strip(), "codigo": codigo})
    return salida