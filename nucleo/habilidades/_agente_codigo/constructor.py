"""
nucleo/habilidades/agente_codigo/constructor.py
─────────────────────────────────────────────────────────────────────────────
CREA PROYECTOS DESDE CERO.

Flujo:
    planificar (qué archivos) → generar cada archivo → verificar sintaxis →
    escribir en proyectos/<nombre>/ (por el GOBERNADOR) → informar.

Después el proyecto queda en proyectos/ y se mantiene/extiende con el flujo
normal de misiones (agente.ejecutar_mision), que ya verifica por ejecución.

La generación va por cerebro.pensar_codigo (modelo de código). Ese es el punto
único donde, el día de mañana, enchufás un modelo local en vez de Groq.
"""
import json
import logging
import re
from pathlib import Path

from . import cerebro, proyectos

log = logging.getLogger("satella.agente.constructor")

try:
    from nucleo.habilidades.gobernador import motor as _gob, politica as _gpol
    _gob_ok = True
except Exception:
    _gob_ok = False


def _permitido(objetivo: str) -> tuple:
    if not _gob_ok:
        return True, "sin gobernador"
    v = _gob.evaluar("crear proyecto en proyectos/", nivel=_gpol.ESCRITURA,
                     objetivo=objetivo, propio=True)
    if v["veredicto"] == _gpol.PERMITIDO:
        return True, v["razon"]
    if v["veredicto"] == _gpol.CONFIRMAR:
        return False, f"requiere tu confirmación (token {v.get('token')})"
    return False, f"denegado: {v['razon']}"


def _json_de(texto: str):
    if not texto:
        return None
    t = texto.strip()
    t = re.sub(r"^```[a-zA-Z]*\n", "", t)
    t = re.sub(r"\n```$", "", t)
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _sin_fences(texto: str) -> str:
    t = (texto or "").strip()
    t = re.sub(r"^```[a-zA-Z0-9]*\n", "", t)
    t = re.sub(r"\n```$", "", t)
    return t


def planificar(descripcion: str):
    sistema = (
        "Sos un arquitecto de software. Te dan una idea y devolvés SOLO un JSON "
        "(sin explicaciones, sin ```), con esta forma EXACTA:\n"
        '{"nombre":"slug_corto_sin_espacios",'
        '"archivos":[{"ruta":"main.py","proposito":"qué hace este archivo"}],'
        '"entrada":"main.py","como_correr":"python main.py"}\n'
        "Diseñá un proyecto CHICO y AUTÓNOMO: que corra con Python puro, sin librerías "
        "externas salvo que la idea lo exija de verdad. Pocos archivos, bien separados "
        "por responsabilidad. El campo 'entrada' es el archivo que se ejecuta."
    )
    resp = cerebro.pensar_codigo(f"IDEA: {descripcion}", sistema)
    return _json_de(resp)


def _generar_archivo(descripcion: str, plan: dict, archivo: dict, ya_generados: dict) -> str:
    otros = ", ".join(a.get("ruta", "") for a in plan.get("archivos", []))
    sistema = (
        "Generás el contenido COMPLETO de UN archivo de un proyecto. Devolvés SOLO el "
        "código del archivo: sin explicaciones, sin ```. Código limpio y funcional, "
        "comentado donde ayude. Es parte de un proyecto con estos archivos: " + otros + ". "
        "Si otro archivo YA implementa algo (te lo paso abajo), IMPORTÁLO y reutilizalo; "
        "NO redefinas ni dupliques esa lógica. Respetá los nombres reales para los imports."
    )
    prompt = (f"PROYECTO: {descripcion}\n"
              f"ARCHIVO A ESCRIBIR: {archivo.get('ruta')}\n"
              f"PROPÓSITO: {archivo.get('proposito', '')}")
    if ya_generados:
        bloques = "\n\n".join(
            f"# {ruta} (YA generado — usalo, no lo reimplementes):\n{cont}"
            for ruta, cont in ya_generados.items()
        )
        prompt += f"\n\nARCHIVOS YA GENERADOS DEL PROYECTO:\n{bloques}"
    prompt += "\n\nEscribí el archivo completo."
    return _sin_fences(cerebro.pensar_codigo(prompt, sistema))


def crear_proyecto(descripcion: str, nombre_forzado: str = None) -> dict:
    if not cerebro.disponible():
        return {"estado": "error", "informe": "El cerebro de código no está disponible (revisá GROQ_API_KEY / GROQ_MODEL_CODIGO)."}

    plan = planificar(descripcion)
    if not plan or not plan.get("archivos"):
        return {"estado": "error", "informe": "No pude armar un plan válido del proyecto. Describímelo un poco más concreto (qué hace, qué partes tiene)."}

    nombre = nombre_forzado or plan.get("nombre") or "proyecto_nuevo"
    destino = proyectos.ruta(nombre)
    if destino.exists():
        return {"estado": "error", "informe": f"Ya existe proyectos/{destino.name}. Usá otro nombre o borralo primero."}

    puede, razon = _permitido(str(destino))
    if not puede:
        return {"estado": "error", "informe": f"Gobernador: {razon}"}

    creados, fallos = [], []
    ya_generados = {}
    # generar primero los archivos base y el de ENTRADA al final, así puede importar al resto
    entrada = plan.get("entrada")
    orden = sorted(plan["archivos"], key=lambda a: 1 if a.get("ruta") == entrada else 0)
    for arch in orden:
        ruta_rel = (arch.get("ruta") or "").strip().lstrip("/\\")
        if not ruta_rel:
            continue
        contenido = _generar_archivo(descripcion, plan, arch, ya_generados)
        if not contenido:
            fallos.append(f"{ruta_rel}: el modelo no generó contenido")
            continue
        if ruta_rel.endswith(".py"):
            try:
                compile(contenido, ruta_rel, "exec")
            except SyntaxError as e:
                fallos.append(f"{ruta_rel}: error de sintaxis ({e})")
                continue
        try:
            archivo_destino = destino / ruta_rel
            archivo_destino.parent.mkdir(parents=True, exist_ok=True)
            archivo_destino.write_text(contenido, encoding="utf-8")
            creados.append(ruta_rel)
            ya_generados[ruta_rel] = contenido
            log.info(f"[CONSTRUCTOR] escrito {nombre}/{ruta_rel} ({len(contenido)} chars)")
        except Exception as e:
            fallos.append(f"{ruta_rel}: no pude escribir ({e})")

    if not creados:
        return {"estado": "error", "informe": "No se creó ningún archivo. " + "; ".join(fallos)}

    informe = (f"Creé el proyecto «{nombre}» en proyectos/{destino.name} con {len(creados)} archivo(s): "
               + ", ".join(creados))
    if plan.get("como_correr"):
        informe += f"\nPara correrlo: entrá a la carpeta y corré `{plan['como_correr']}`."
    if fallos:
        informe += "\nQuedaron con problema: " + "; ".join(fallos)
    informe += "\nDespués lo extendés diciendo «agente, en " + nombre + ", en <archivo>: <qué cambiar>»."
    return {"estado": "ok", "informe": informe, "nombre": nombre, "creados": creados, "fallos": fallos}