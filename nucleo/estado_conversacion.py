"""
nucleo/estado_conversacion.py
Estado vivo de conversación — el "yo" que persiste entre turnos.

Resuelve el problema central: el motor sabía lo que dijo Sebastian
pero no sabía lo que SATELLA dijo. Ahora sabe ambos, sabe el tipo
de cada mensaje, y detecta si el mensaje actual es un seguimiento
de algo que Satella afirmó.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

log = logging.getLogger("satella.estado")

@dataclass
class Turno:
    hablante: str            # "satella" | "sebastian"
    texto: str
    tipo: str                # OBSERVACION | PREGUNTA | AFIRMACION | SALUDO | ...
    implicaciones: list      # lo que el texto implica (extraído en runtime)
    temas: list              # temas mencionados
    ts: str = field(default_factory=lambda: datetime.now().isoformat())


class EstadoConversacion:
    """
    Estado estructurado de la conversación.
    No guarda solo texto — guarda semántica: qué tipo fue, qué implica,
    qué temas abrió, si el siguiente mensaje lo está siguiendo.
    """

    _PATRONES_SEGUIMIENTO = [
        r"^y qu[eé]",           # "y que te dice eso"
        r"^y eso",              # "y eso qué significa"
        r"^qu[eé] significa",   # "qué significa lo que dijiste"
        r"^por qu[eé] dijiste", # "por qué dijiste eso"
        r"^a qu[eé] te referís",
        r"^qu[eé] quisiste",
        r"^explic[aá]me",
        r"^y la parte",
        r"^y eso de",
        r"^cómo así",
        r"^como así",
        r"^no entend",
        r"^qu[eé] queres decir",
        r"^qu[eé] querés decir",
        r"pues t[uú] lo dijiste",
        r"lo que dijiste",
        r"lo que dij[io]ste",
        r"según t[uú]",
        r"segun tu",
    ]

    _TIPOS_SATELLA = {
        "observacion":  ["fascin","observo","noto","hay algo","lo que describ","la diferencia"],
        "pregunta":     ["?","¿"],
        "afirmacion":   ["siempre","nunca","es que","el problema","la razón","lo que pasa"],
        "desafio":      ["barusu","¡ahah","inconsistencia","prueba","interesante que"],
        "apoyo":        ["creí en vos","me importa","te importa","genuinamente"],
    }

    # Extrae la implicación semántica de frases de Satella
    _IMPLICACIONES = [
        (r"querés medirme sin decirme con qué metro",
         "buscás validación sin comprometerte primero"),
        (r"la evaluación ya empezó",
         "el test estaba corriendo antes de pedirlo"),
        (r"hay algo .* que no (nombraste|dijiste|cerraste)",
         "hay algo que evitás nombrar"),
        (r"la pregunta que no hiciste",
         "la pregunta real es diferente a la que planteaste"),
        (r"suposición implícita",
         "hay una suposición que no verificaste"),
        (r"punto que evitás",
         "hay algo que conscientemente no querés decir"),
        (r"resistencia aparece antes",
         "el problema no es la tarea sino el umbral de entrada"),
        (r"criterio .* más exigente",
         "te medís con un estándar que no le aplicarías a otros"),
        (r"brecha entre lo que decís .* y lo que hacés",
         "hacés más de lo que reconocés en voz alta"),
    ]

    def __init__(self):
        self.historial: list[Turno] = []
        self._ultimo_satella: Optional[Turno] = None
        self._ultimo_sebastian: Optional[Turno] = None
        self.temas_abiertos: list[dict] = []
        self.modo_voz: str = "echidna"

    # ── Registro ─────────────────────────────────────────────────────────────

    def registrar(self, hablante: str, texto: str, tipo: str = ""):
        if not tipo:
            tipo = self._detectar_tipo(hablante, texto)
        implicaciones = self._extraer_implicaciones(texto) if hablante == "satella" else []
        temas = self._extraer_temas(texto)

        turno = Turno(hablante=hablante, texto=texto,
                      tipo=tipo, implicaciones=implicaciones, temas=temas)
        self.historial.append(turno)
        self.historial = self.historial[-20:]  # ventana de 20 turnos

        if hablante == "satella":
            self._ultimo_satella = turno
            for tema in temas:
                self.temas_abiertos.append({"tema": tema, "desde": "satella", "turno": len(self.historial)})
        else:
            self._ultimo_sebastian = turno

    # ── Queries ──────────────────────────────────────────────────────────────

    def es_seguimiento(self, mensaje: str) -> bool:
        """¿Sebastian está preguntando sobre algo que Satella dijo?"""
        ml = mensaje.lower().strip()
        for patron in self._PATRONES_SEGUIMIENTO:
            if re.search(patron, ml):
                return True
        return False

    def ultimo_satella(self) -> Optional[Turno]:
        return self._ultimo_satella

    def ultimo_sebastian(self) -> Optional[Turno]:
        return self._ultimo_sebastian

    def implicacion_activa(self) -> str:
        """La implicación más reciente de una afirmación de Satella."""
        if self._ultimo_satella and self._ultimo_satella.implicaciones:
            return self._ultimo_satella.implicaciones[0]
        return ""

    def texto_satella_corto(self) -> str:
        """Fragmento corto de lo que Satella dijo — para citar en la respuesta."""
        if not self._ultimo_satella:
            return ""
        texto = self._ultimo_satella.texto
        # Tomar hasta el primer punto o 60 chars
        match = re.match(r"[^.!?]+[.!?]?", texto)
        if match:
            return match.group().strip()
        return texto[:60].strip()

    def contexto_para_compositor(self) -> dict:
        """Diccionario de variables disponibles para las plantillas."""
        ctx = {
            "ultimo_satella_texto": self._ultimo_satella.texto if self._ultimo_satella else "",
            "ultimo_satella_corto": self.texto_satella_corto(),
            "implicacion": self.implicacion_activa(),
            "tipo_ultimo_satella": self._ultimo_satella.tipo if self._ultimo_satella else "",
            "ultimo_sebastian_texto": self._ultimo_sebastian.texto if self._ultimo_sebastian else "",
            "temas_abiertos": [t["tema"] for t in self.temas_abiertos[-3:]],
            "modo_voz": self.modo_voz,
            "hay_seguimiento": False,
            "hay_historial": len(self.historial) > 2,
        }
        return ctx

    def snapshot(self) -> dict:
        return {
            "turnos": len(self.historial),
            "ultimo_satella": self._ultimo_satella.texto[:80] if self._ultimo_satella else None,
            "modo_voz": self.modo_voz,
        }

    # ── Internos ─────────────────────────────────────────────────────────────

    def _detectar_tipo(self, hablante: str, texto: str) -> str:
        tl = texto.lower()
        if "?" in texto or "¿" in texto:
            return "pregunta"
        if hablante == "satella":
            for tipo, señales in self._TIPOS_SATELLA.items():
                if any(s in tl for s in señales):
                    return tipo
        return "afirmacion"

    def _extraer_implicaciones(self, texto: str) -> list:
        tl = texto.lower()
        implicaciones = []
        for patron, implicacion in self._IMPLICACIONES:
            if re.search(patron, tl):
                implicaciones.append(implicacion)
        return implicaciones

    def _extraer_temas(self, texto: str) -> list:
        temas = []
        tl = texto.lower()
        _TEMAS = {
            "bell": ["bell","belladonna"],
            "satella": ["satella","motor","sistema"],
            "sebastian": ["sebastian","sebas","barusu","vos","yo"],
            "trabajo": ["trabajo","jelcon","proyecto"],
            "universidad": ["universidad","materia","parcial","clase"],
            "personalidad": ["personalidad","echidna","voz","profundidad"],
        }
        for tema, palabras in _TEMAS.items():
            if any(p in tl for p in palabras):
                temas.append(tema)
        return temas