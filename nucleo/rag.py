"""
RAG de Satella — adaptado de abelardo-bot-backend.
Tokenización con normalización de acentos, scoring por párrafo.
Lee archivos .txt en datos/conocimiento/
"""
import re
import os
import logging
from config import CONOCIMIENTO_DIR

log = logging.getLogger("satella.rag")
_docs_cache: list[dict] = []


def _norm(text: str) -> str:
    t = text.lower()
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),
                 ('ü','u'),('ñ','n'),('à','a'),('è','e'),('ì','i'),
                 ('ò','o'),('ù','u')]:
        t = t.replace(a, b)
    return t


def _tokenize(text: str) -> set:
    words = re.findall(r'\b[a-záéíóúüñ]{3,}\b', _norm(text))
    stop = {
        'que','con','los','las','del','una','por','para','son','sus',
        'nos','mas','pero','como','esta','este','esto','ser','hay',
        'fue','han','tiene','van','sea','muy','bien','cuando','donde',
        'porque','sobre','entre','todo','todos','cada','solo','sin',
        'the','and','for','are','was','this','with','from','una','unos',
        'unas','aqui','ahi','alla','esto','eso','aquello','algun','alguna',
    }
    return {w for w in words if w not in stop}


def cargar_documentos() -> int:
    global _docs_cache
    _docs_cache = []
    os.makedirs(CONOCIMIENTO_DIR, exist_ok=True)

    for fname in os.listdir(CONOCIMIENTO_DIR):
        if not fname.endswith('.txt'):
            continue
        path = os.path.join(CONOCIMIENTO_DIR, fname)
        try:
            with open(path, encoding='utf-8') as f:
                content = f.read().strip()
            if content:
                _docs_cache.append({
                    'titulo': fname.replace('.txt','').replace('_',' '),
                    'contenido': content,
                    'archivo': fname,
                })
        except Exception as e:
            log.error(f"RAG: error leyendo {fname}: {e}")

    log.info(f"RAG: {len(_docs_cache)} documentos cargados")
    return len(_docs_cache)


def agregar_conocimiento(titulo: str, contenido: str, archivo: str = None) -> bool:
    """Agrega un nuevo documento al RAG en tiempo de ejecución."""
    try:
        if not archivo:
            archivo = titulo.lower().replace(' ', '_') + '.txt'
        path = os.path.join(CONOCIMIENTO_DIR, archivo)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"== {titulo.upper()} ==\n\n{contenido}")
        _docs_cache.append({
            'titulo': titulo,
            'contenido': contenido,
            'archivo': archivo,
        })
        return True
    except Exception as e:
        log.error(f"RAG: error agregando conocimiento: {e}")
        return False


def consultar(query: str, k: int = 3) -> str:
    """
    Busca los párrafos más relevantes para el query.
    Retorna string con los top-k párrafos separados por '---'.
    """
    if not _docs_cache:
        return ""

    query_tokens = _tokenize(query)
    if not query_tokens:
        return ""

    scored: list[tuple[float, str]] = []

    for doc in _docs_cache:
        doc_tokens = _tokenize(doc['titulo'] + ' ' + doc['contenido'])
        titulo_match = query_tokens & _tokenize(doc['titulo'])
        titulo_bonus = len(titulo_match) * 0.5

        paragraphs = [p.strip() for p in re.split(r'\n{2,}', doc['contenido'])
                      if len(p.strip()) > 30]

        for para in paragraphs:
            para_tokens = _tokenize(para)
            common = query_tokens & para_tokens
            if common:
                score = (len(common) / max(len(query_tokens), 1)) + titulo_bonus
                scored.append((score, para))

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [text for _, text in scored[:k]]
    return "\n\n---\n\n".join(top)