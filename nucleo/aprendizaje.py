"""
aprendizaje.py — Sistema de aprendizaje continuo de Satella.

Tres niveles:
1. Inmediato: cada turno se guarda como dato de entrenamiento
2. Correcciones: Sebastian dice "no, así no" → se guarda permanentemente
3. Feedback: refuerza o debilita patrones según respuesta de Sebastian

No necesita reentrenamiento. No necesita GPU.
El conocimiento se actualiza en el siguiente mensaje.
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional

log = logging.getLogger("satella.aprendizaje")

DATOS_DIR = os.path.join(os.path.dirname(__file__), "..", "datos")
ENTRENAMIENTO_PATH = os.path.join(DATOS_DIR, "datos_entrenamiento.json")
CORRECCIONES_PATH  = os.path.join(DATOS_DIR, "correcciones.json")
MODELO_SEB_PATH    = os.path.join(DATOS_DIR, "modelo_sebastian.json")

# Señales de corrección en el lenguaje de Sebastian
SEÑALES_CORRECCION = [
    "no, eso", "eso está mal", "te equivocas", "no es así",
    "en realidad", "la solución es", "no, la forma", "eso no es correcto",
    "no, el código", "no, debería ser", "ese approach está mal",
    "no, eso no", "eso no se hace así", "incorrecto"
]

# Señales de feedback positivo
SEÑALES_POSITIVO = [
    "eso estuvo bien", "exactamente", "eso era lo que", "perfecto",
    "muy bien", "me gustó", "genial", "sí, eso", "correcto",
    "justo lo que", "brillante", "excelente"
]

# Señales de feedback negativo
SEÑALES_NEGATIVO = [
    "eso no era", "no me gustó", "no era lo que", "no es correcto",
    "no sirve", "está mal", "no me ayuda", "no entendiste"
]


class RegistradorAprendizaje:
    """
    Registra todo lo que pasa en las conversaciones para que Satella aprenda.
    Detecta correcciones y feedback automáticamente del lenguaje natural.
    """

    def __init__(self, motor_ref=None):
        self.motor = motor_ref
        self._datos_entrenamiento: list = []
        self._ultimo_patron_usado: Optional[str] = None
        self._ultima_situacion_usada: Optional[str] = None
        self._cargar()

    def _cargar(self):
        try:
            if os.path.exists(ENTRENAMIENTO_PATH):
                with open(ENTRENAMIENTO_PATH, encoding="utf-8") as f:
                    self._datos_entrenamiento = json.load(f)
            log.info(f"[APRENDIZAJE] {len(self._datos_entrenamiento)} datos de entrenamiento cargados")
        except Exception as e:
            log.error(f"[APRENDIZAJE] Error cargando datos: {e}")
            self._datos_entrenamiento = []

    def _guardar(self):
        try:
            with open(ENTRENAMIENTO_PATH, "w", encoding="utf-8") as f:
                json.dump(self._datos_entrenamiento, f,
                          ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"[APRENDIZAJE] Error guardando: {e}")

    # ─── REGISTRO DE CADA TURNO ───────────────────────────────────────────────

    def registrar_turno(self, mensaje: str, respuesta: str,
                         situacion: str, patron_id: Optional[str],
                         usando_motor: bool, confianza: float,
                         comprension: dict, contexto_sebastian: dict):
        """
        Guarda cada intercambio como dato de entrenamiento futuro.
        Este es el material crudo del que Satella aprende.
        """
        self._ultimo_patron_usado   = patron_id
        self._ultima_situacion_usada = situacion

        entrada = {
            "fecha": datetime.now().isoformat(),
            "input": {
                "mensaje": mensaje,
                "tono": comprension.get("tono", ""),
                "necesita": comprension.get("necesita", ""),
                "intencion_real": comprension.get("intencion_real", ""),
                "proyecto_activo": contexto_sebastian.get("proyectos", {}),
            },
            "output": {
                "respuesta": respuesta,
                "situacion": situacion,
                "patron_id": patron_id,
                "usando_motor": usando_motor,
                "confianza_clasificacion": confianza,
            },
            "calidad": "sin_evaluar",
        }

        self._datos_entrenamiento.append(entrada)

        # Guardar cada 10 turnos para no escribir en disco en cada mensaje
        if len(self._datos_entrenamiento) % 10 == 0:
            self._guardar()
            log.info(f"[APRENDIZAJE] {len(self._datos_entrenamiento)} ejemplos guardados")

    # ─── DETECCIÓN AUTOMÁTICA DE CORRECCIONES Y FEEDBACK ─────────────────────

    def analizar_mensaje_entrante(self, mensaje: str) -> dict:
        """
        Analiza si el mensaje de Sebastian contiene:
        - Una corrección a algo que Satella dijo
        - Feedback positivo
        - Feedback negativo

        Retorna: {"tipo": "correccion|positivo|negativo|normal", "señal": str}
        """
        msg_lower = mensaje.lower()

        for señal in SEÑALES_CORRECCION:
            if señal in msg_lower:
                return {"tipo": "correccion", "señal": señal}

        for señal in SEÑALES_POSITIVO:
            if señal in msg_lower:
                return {"tipo": "positivo", "señal": señal}

        for señal in SEÑALES_NEGATIVO:
            if señal in msg_lower:
                return {"tipo": "negativo", "señal": señal}

        return {"tipo": "normal", "señal": ""}

    def procesar_correccion(self, mensaje_correccion: str,
                             respuesta_incorrecta: str,
                             contexto: dict):
        """
        Sebastian dijo que algo estaba mal.
        Guarda la corrección permanentemente y ajusta el patrón.
        """
        log.info(f"[APRENDIZAJE] Corrección detectada: {mensaje_correccion[:60]}")

        # Guardar en el motor
        if self.motor:
            self.motor.guardar_correccion(
                mensaje_sebastian=mensaje_correccion,
                respuesta_incorrecta=respuesta_incorrecta,
                situacion=self._ultima_situacion_usada or "DESCONOCIDA",
                contexto=contexto
            )

            # Debilitar el patrón que generó la respuesta incorrecta
            if self._ultimo_patron_usado and self._ultima_situacion_usada:
                self.motor.ajustar_peso_patron(
                    situacion_id=self._ultima_situacion_usada,
                    patron_id=self._ultimo_patron_usado,
                    delta=-0.3
                )

        # Marcar el último ejemplo de entrenamiento como incorrecto
        if self._datos_entrenamiento:
            self._datos_entrenamiento[-1]["calidad"] = "incorrecto"
            self._guardar()

    def procesar_feedback_positivo(self, mensaje: str):
        """Sebastian indicó que algo funcionó bien."""
        log.info(f"[APRENDIZAJE] Feedback positivo detectado")

        if self.motor and self._ultimo_patron_usado and self._ultima_situacion_usada:
            self.motor.ajustar_peso_patron(
                situacion_id=self._ultima_situacion_usada,
                patron_id=self._ultimo_patron_usado,
                delta=+0.2
            )

        if self._datos_entrenamiento:
            self._datos_entrenamiento[-1]["calidad"] = "excelente"
            self._guardar()

    def procesar_feedback_negativo(self, mensaje: str):
        """Sebastian indicó que algo no funcionó."""
        log.info(f"[APRENDIZAJE] Feedback negativo detectado")

        if self.motor and self._ultimo_patron_usado and self._ultima_situacion_usada:
            self.motor.ajustar_peso_patron(
                situacion_id=self._ultima_situacion_usada,
                patron_id=self._ultimo_patron_usado,
                delta=-0.15
            )

        if self._datos_entrenamiento:
            self._datos_entrenamiento[-1]["calidad"] = "malo"
            self._guardar()

    # ─── ACTUALIZACIÓN DEL MODELO DE SEBASTIAN ───────────────────────────────

    def actualizar_modelo_sebastian(self, comprension: dict,
                                     mensaje: str, contexto: dict):
        """
        Detecta información nueva sobre Sebastian en el mensaje
        y actualiza modelo_sebastian.json automáticamente.
        """
        try:
            with open(MODELO_SEB_PATH, encoding="utf-8") as f:
                modelo = json.load(f)
        except Exception:
            return

        actualizado = False

        # Detectar menciones de proyectos nuevos
        palabras = mensaje.lower().split()
        proyectos_conocidos = set(modelo.get("proyectos", {}).keys())

        # Detectar estado emocional predominante
        tono = comprension.get("tono", "")
        if tono and "patrones" not in modelo:
            modelo["patrones"] = {}
        if tono:
            modelo["patrones"]["ultimo_tono"] = tono
            modelo["patrones"]["ultima_actividad"] = datetime.now().isoformat()
            actualizado = True

        # Detectar horario de actividad
        hora_actual = datetime.now().hour
        if 22 <= hora_actual or hora_actual < 4:
            modelo["patrones"]["horario_activo"] = "noche"
            actualizado = True

        if actualizado:
            try:
                with open(MODELO_SEB_PATH, "w", encoding="utf-8") as f:
                    json.dump(modelo, f, ensure_ascii=False, indent=2)
            except Exception as e:
                log.error(f"[APRENDIZAJE] Error actualizando modelo: {e}")

    # ─── ESTADÍSTICAS DEL MOTOR ───────────────────────────────────────────────

    def estadisticas(self) -> dict:
        """Retorna métricas de aprendizaje del motor."""
        total = len(self._datos_entrenamiento)
        if total == 0:
            return {"total": 0}

        usando_motor = sum(1 for d in self._datos_entrenamiento
                           if d["output"].get("usando_motor"))
        excelentes   = sum(1 for d in self._datos_entrenamiento
                           if d.get("calidad") == "excelente")
        incorrectos  = sum(1 for d in self._datos_entrenamiento
                           if d.get("calidad") == "incorrecto")

        return {
            "total_ejemplos": total,
            "usando_motor_pct": round(usando_motor / total * 100, 1),
            "calidad_excelente": excelentes,
            "calidad_incorrecta": incorrectos,
            "pendientes_evaluar": total - excelentes - incorrectos,
        }

    def flush(self):
        """Fuerza guardado inmediato."""
        self._guardar()