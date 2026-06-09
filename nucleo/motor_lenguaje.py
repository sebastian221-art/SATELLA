"""
motor_lenguaje.py — Motor de lenguaje propio de Satella.
Arquitectura: clasificación de situación → selección de patrón con diversidad
→ llenado de variables con contexto real → respuesta sin LLM.

Filosofía: la inteligencia está en la arquitectura (patrones + taxonomía),
no en el cómputo. Corre en RAM mínima, sin GPU, sin API.
"""
import json
import logging
import os
import re
import random
from datetime import datetime
from typing import Optional

log = logging.getLogger("satella.motor")

DATOS_DIR = os.path.join(os.path.dirname(__file__), "..", "datos")
TAXONOMIA_PATH  = os.path.join(DATOS_DIR, "taxonomia_situaciones.json")
PATRONES_PATH   = os.path.join(DATOS_DIR, "biblioteca_patrones.json")
CORRECCIONES_PATH = os.path.join(DATOS_DIR, "correcciones.json")

UMBRAL_CONFIANZA = 0.75   # Alto deliberadamente — el motor solo entra cuando está MUY seguro
MAX_USOS_RECIENTES = 3    # Cuántos usos recientes trackea por patrón


class MotorLenguaje:
    """
    Motor de patrones conversacionales de Satella.
    Aprende, varía, nunca repite, nunca alucina.
    """

    def __init__(self):
        self.taxonomia: dict = {}
        self.patrones: dict = {}
        self.correcciones: list = []
        self._cargado = False

    def cargar(self) -> int:
        """Carga taxonomía, patrones y correcciones. Retorna total de patrones."""
        try:
            with open(TAXONOMIA_PATH, encoding="utf-8") as f:
                data = json.load(f)
                self.taxonomia = data.get("situaciones", {})

            with open(PATRONES_PATH, encoding="utf-8") as f:
                self.patrones = json.load(f)

            if os.path.exists(CORRECCIONES_PATH):
                with open(CORRECCIONES_PATH, encoding="utf-8") as f:
                    self.correcciones = json.load(f)
            else:
                self.correcciones = []

            total = sum(len(v) for v in self.patrones.values()
                        if isinstance(v, list))
            self._cargado = True
            log.info(f"[MOTOR] {len(self.taxonomia)} situaciones | "
                     f"{total} patrones | {len(self.correcciones)} correcciones")
            return total
        except Exception as e:
            log.error(f"[MOTOR] Error cargando: {e}")
            return 0

    # ─── CLASIFICACIÓN DE SITUACIÓN ──────────────────────────────────────────

    def clasificar(self, mensaje: str, comprension: dict) -> tuple[str, float]:
        """
        Retorna (situacion_id, confianza 0.0-1.0).
        Combina señales lingüísticas + comprensión del C1.
        """
        if not self._cargado:
            self.cargar()

        msg_lower = mensaje.lower()
        tono      = comprension.get("tono", "")
        necesita  = comprension.get("necesita", "")
        proyecto  = comprension.get("proyecto_activo", "")

        scores: dict[str, float] = {}

        for sit_id, sit in self.taxonomia.items():
            score = 0.0

            # Señales lingüísticas en el mensaje
            for señal in sit.get("señales_linguisticas", []):
                if señal.lower() in msg_lower:
                    score += 0.35

            # Señales de comprensión
            for sc in sit.get("señales_comprension", []):
                if "tono=" in sc:
                    tonos_sit = sc.replace("tono=", "").split("|")
                    for t in tonos_sit:
                        if t in tono:
                            score += 0.25
                elif "necesita=" in sc:
                    nec_sit = sc.replace("necesita=", "").split("|")
                    for n in nec_sit:
                        if n in necesita:
                            score += 0.20
                elif "proyecto_activo=" in sc:
                    proyectos_sit = sc.replace("proyecto_activo=", "").split("|")
                    for p in proyectos_sit:
                        if p.lower() in (proyecto or "").lower():
                            score += 0.15

            if score > 0:
                scores[sit_id] = min(score, 1.0)

        if not scores:
            return "SMALL_TALK", 0.3

        mejor = max(scores, key=scores.get)
        return mejor, scores[mejor]

    # ─── SELECCIÓN DE PATRÓN CON DIVERSIDAD ──────────────────────────────────

    def seleccionar_patron(self, situacion_id: str) -> Optional[dict]:
        """
        Selecciona el mejor patrón para la situación,
        evitando los usados recientemente.
        """
        candidatos = self.patrones.get(situacion_id, [])
        if not candidatos:
            return None

        # Filtrar los usados recientemente
        disponibles = [
            p for p in candidatos
            if len(p.get("usos_recientes", [])) == 0
            or p["id"] not in p.get("usos_recientes", [])[-MAX_USOS_RECIENTES:]
        ]

        if not disponibles:
            # Si todos fueron usados recientemente, limpiar tracker
            for p in candidatos:
                p["usos_recientes"] = []
            disponibles = candidatos

        # Selección ponderada por peso
        pesos = [p.get("peso", 1.0) for p in disponibles]
        total_peso = sum(pesos)
        if total_peso == 0:
            return random.choice(disponibles)

        r = random.uniform(0, total_peso)
        acumulado = 0.0
        for patron, peso in zip(disponibles, pesos):
            acumulado += peso
            if r <= acumulado:
                return patron

        return disponibles[-1]

    def _registrar_uso(self, situacion_id: str, patron_id: str):
        """Registra que este patrón fue usado (para el tracker de diversidad)."""
        candidatos = self.patrones.get(situacion_id, [])
        for p in candidatos:
            if p["id"] == patron_id:
                if "usos_recientes" not in p:
                    p["usos_recientes"] = []
                p["usos_recientes"].append(patron_id)
                if len(p["usos_recientes"]) > MAX_USOS_RECIENTES * 2:
                    p["usos_recientes"] = p["usos_recientes"][-MAX_USOS_RECIENTES:]
                break

    # ─── LLENADO DE VARIABLES ────────────────────────────────────────────────

    def _llenar_patron(self, patron: dict, mensaje: str,
                        sebastian: dict, episodios: list) -> str:
        """
        Llena las variables de la plantilla del patrón con contenido real.
        """
        estructura = patron.get("estructura", "")
        variables  = patron.get("variables", {})

        if not variables:
            return estructura

        rellenos: dict[str, str] = {}

        # Extraer datos de Sebastian
        proyectos   = sebastian.get("proyectos", {})
        nombre      = sebastian.get("apodo", "Sebas")
        proy_activo = next(
            (k for k, v in proyectos.items() if v.get("estado") == "activo"),
            "tu proyecto"
        )

        # Último episodio
        ultimo_ep   = episodios[-1] if episodios else {}
        # "sesión general" es el default vacío del sintetizador — ignorarlo
        _raw_tema   = ultimo_ep.get("tema_principal", "")
        ultimo_tema = "" if _raw_tema in ("sesión general", "general", "") else _raw_tema
        pendientes  = ultimo_ep.get("pendientes", [])
        estado      = ultimo_ep.get("estado_sebastian", "normal")

        # Extraer términos del mensaje actual
        palabras_clave = [w for w in mensaje.lower().split()
                          if len(w) > 4 and w not in
                          {"tengo", "quiero", "puedo", "siento", "como", "esto", "para"}]
        termino_sebastian = palabras_clave[0] if palabras_clave else "eso"

        for var_nombre, var_tipo in variables.items():
            valor = ""

            if var_tipo in ("proyecto_activo", "proyecto_principal", "Bell o Satella",
                            "Bell o Satella", "proyecto", "proyectos"):
                valor = proy_activo

            elif var_tipo in ("palabra_usada", "termino", "palabra_que_uso"):
                valor = termino_sebastian

            elif var_tipo in ("logro_real_conocido", "logro_especifico",
                              "logro_concreto_de_sebastian"):
                logros = sebastian.get("logros", [])
                valor  = logros[0] if logros else f"haber construido {proy_activo}"

            elif var_tipo in ("ultimo_tema", "tema", "tema_anterior",
                              "tema_reciente", "ultimo_proyecto_mencionado"):
                valor = ultimo_tema or proy_activo

            elif var_tipo == "ultimo_estado_conocido":
                valor = estado

            elif var_tipo in ("nombre_sebastian", "Juan Sebastian"):
                valor = sebastian.get("nombre", "Juan Sebastian").split()[1] if sebastian.get("nombre") else "Sebastian"

            elif var_tipo == "emocion_expresada":
                for emocion in ["cansado", "frustrado", "triste", "ansioso",
                                "bien", "mal", "aburrido"]:
                    if emocion in mensaje.lower():
                        valor = emocion
                        break
                valor = valor or "así"

            elif var_tipo in ("ultimo_tema_sin_resolver", "algo_pendiente_anterior"):
                valor = (pendientes[0] if pendientes else
                         ultimo_tema or f"lo de {proy_activo}")

            elif var_tipo in ("tarea", "lo que evade", "tarea_especifica",
                              "tarea_evadida"):
                # Detectar qué tarea menciona
                for palabra in ["tarea", "trabajo", "parcial", "examen",
                                "proyecto", "cálculo", "materia"]:
                    if palabra in mensaje.lower():
                        valor = palabra
                        break
                valor = valor or "eso"

            elif var_tipo == "algo_de_sebastian":
                valor = ultimo_tema or proy_activo

            elif var_tipo == "resumen_de_una_linea":
                valor = f"quedó claro lo de {ultimo_tema}" if ultimo_tema else "avanzaste"

            elif var_tipo == "siguiente_paso_obvio":
                valor = pendientes[0] if pendientes else "el siguiente paso"

            else:
                # Variable no mapeada — usar valor genérico inteligente
                valor = var_tipo if len(var_tipo) < 30 else termino_sebastian

            rellenos[var_nombre] = valor or "eso"

        resultado = estructura
        for var, val in rellenos.items():
            resultado = resultado.replace("{" + var + "}", val)

        # Limpiar variables no llenadas
        resultado = re.sub(r'\{[^}]+\}', '', resultado).strip()
        resultado = re.sub(r'\s+', ' ', resultado)

        return resultado

    # ─── ENTRADA PRINCIPAL ───────────────────────────────────────────────────

    def responder(self, mensaje: str, comprension: dict,
                  sebastian: dict, episodios: list,
                  rag_contexto: str = "") -> dict:
        """
        Intenta generar una respuesta usando el motor de patrones.

        Retorna:
          {
            "respuesta": str,
            "situacion": str,
            "patron_id": str,
            "confianza": float,
            "usando_motor": bool
          }
        """
        if not self._cargado:
            self.cargar()

        situacion_id, confianza = self.clasificar(mensaje, comprension)

        # SALUDO solo puede disparar si no hay historial activo en esta sesión
        # (evita que "como estás" mid-conversación active el patrón de saludo)
        if situacion_id == "SALUDO" and len(episodios) > 0:
            log.info("[MOTOR] SALUDO bloqueado mid-conversación — cede a Groq")
            return {"respuesta": None, "situacion": "SMALL_TALK",
                    "patron_id": None, "confianza": 0.0, "usando_motor": False}

        log.info(f"[MOTOR] situacion={situacion_id} | confianza={confianza:.2f}")

        if confianza < UMBRAL_CONFIANZA:
            log.info(f"[MOTOR] Confianza insuficiente — cede a Groq")
            return {"respuesta": None, "situacion": situacion_id,
                    "patron_id": None, "confianza": confianza,
                    "usando_motor": False}

        patron = self.seleccionar_patron(situacion_id)
        if not patron:
            log.info(f"[MOTOR] Sin patrones para {situacion_id} — cede a Groq")
            return {"respuesta": None, "situacion": situacion_id,
                    "patron_id": None, "confianza": confianza,
                    "usando_motor": False}

        respuesta = self._llenar_patron(patron, mensaje, sebastian, episodios)

        # Verificar que la respuesta tiene sustancia
        if len(respuesta.strip()) < 15:
            log.warning(f"[MOTOR] Respuesta muy corta — cede a Groq")
            return {"respuesta": None, "situacion": situacion_id,
                    "patron_id": patron["id"], "confianza": confianza,
                    "usando_motor": False}

        self._registrar_uso(situacion_id, patron["id"])

        log.info(f"[MOTOR] ✓ patron={patron['id']} | "
                 f"{len(respuesta)} chars | tono={patron.get('tono','?')}")

        return {"respuesta": respuesta, "situacion": situacion_id,
                "patron_id": patron["id"], "confianza": confianza,
                "usando_motor": True}

    # ─── CORRECCIONES ─────────────────────────────────────────────────────────

    def guardar_correccion(self, mensaje_sebastian: str,
                            respuesta_incorrecta: str,
                            situacion: str, contexto: dict):
        """
        Cuando Sebastian corrige algo, lo guarda permanentemente.
        Nunca vuelve a cometer ese error.
        """
        correccion = {
            "fecha": datetime.now().isoformat(),
            "situacion": situacion,
            "mensaje_sebastian": mensaje_sebastian,
            "respuesta_incorrecta": respuesta_incorrecta,
            "contexto_proyecto": contexto.get("proyecto_activo", ""),
            "aprendizaje": mensaje_sebastian,
        }
        self.correcciones.append(correccion)
        self._guardar_correcciones()
        log.info(f"[MOTOR] Corrección guardada: {mensaje_sebastian[:60]}")

    def _guardar_correcciones(self):
        try:
            with open(CORRECCIONES_PATH, "w", encoding="utf-8") as f:
                json.dump(self.correcciones, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"[MOTOR] Error guardando correcciones: {e}")

    def ajustar_peso_patron(self, situacion_id: str,
                             patron_id: str, delta: float):
        """
        Sube o baja el peso de un patrón según feedback.
        delta > 0 = funcionó bien, delta < 0 = no funcionó.
        """
        candidatos = self.patrones.get(situacion_id, [])
        for p in candidatos:
            if p["id"] == patron_id:
                p["peso"] = max(0.1, min(3.0, p.get("peso", 1.0) + delta))
                log.info(f"[MOTOR] Patrón {patron_id} → peso={p['peso']:.2f}")
                break
        self._guardar_patrones()

    def _guardar_patrones(self):
        try:
            with open(PATRONES_PATH, "w", encoding="utf-8") as f:
                json.dump(self.patrones, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"[MOTOR] Error guardando patrones: {e}")


# Instancia global
motor = MotorLenguaje()