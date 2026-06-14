"""
nucleo/habilidades/navegador/ojo.py
EL OJO de Satella. Convierte la página en una LISTA DE ELEMENTOS ACCIONABLES con
selectores EXACTOS y únicos. Como Groq es texto, esto es lo que el cerebro (4B) lee
para decidir el próximo paso.

Selector a prueba de balas: a cada elemento accionable le ponemos un atributo único
`data-sat="N"` y el selector es `[data-sat="N"]`. Así nunca colisiona (ni en sitios
como YouTube que reutilizan el mismo id en muchos elementos) y el índice que elige el
cerebro mapea exacto al elemento. Para los enlaces guardamos el href, así el cerebro
distingue los videos (/watch?v=) de lo demás.
"""

JS_EXTRAER = r"""
() => {
  const sel = 'a, button, input, textarea, select, [role=button], [onclick], [type=submit]';
  const vis = (e) => {
    const r = e.getBoundingClientRect();
    const s = window.getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const etiqueta = (e) => {
    const t = (e.innerText || e.value || e.getAttribute('aria-label') ||
               e.getAttribute('placeholder') || e.getAttribute('title') || '').trim();
    return t.replace(/\s+/g, ' ').slice(0, 90);
  };
  // limpiar marcas de una pasada anterior
  document.querySelectorAll('[data-sat]').forEach((e) => e.removeAttribute('data-sat'));
  const out = [];
  for (const e of document.querySelectorAll(sel)) {
    if (!vis(e)) continue;
    const i = out.length;
    e.setAttribute('data-sat', String(i));
    const tag = e.tagName.toLowerCase();
    let tipo = tag;
    if (tag === 'input') tipo = 'input:' + (e.type || 'text');
    const o = { tag: tag, tipo: tipo, texto: etiqueta(e), selector: '[data-sat="' + i + '"]' };
    if (tag === 'a' && e.getAttribute('href')) o.href = e.getAttribute('href');
    out.push(o);
    if (out.length >= 60) break;
  }
  return out;
}
"""

# Dibuja un número sobre cada elemento accionable VISIBLE (los que ya tienen data-sat
# puestos por JS_EXTRAER). El número coincide con el índice de la lista, así el cerebro
# puede MIRAR la captura y elegir "el [N]" que ve. "Set-of-marks".
JS_MARCAR = r"""
() => {
  const old = document.getElementById('__sat_marks'); if (old) old.remove();
  const cont = document.createElement('div');
  cont.id = '__sat_marks';
  cont.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483646;pointer-events:none;';
  document.body.appendChild(cont);
  const W = window.innerWidth, H = window.innerHeight;
  document.querySelectorAll('[data-sat]').forEach((e) => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    if (r.bottom < 0 || r.top > H || r.right < 0 || r.left > W) return; // fuera de pantalla
    const n = e.getAttribute('data-sat');
    const b = document.createElement('div');
    b.textContent = n;
    const x = Math.max(0, Math.min(W - 24, r.left));
    const y = Math.max(0, Math.min(H - 16, r.top));
    b.style.cssText = 'position:fixed;left:' + x + 'px;top:' + y + 'px;background:#ff2d55;' +
      'color:#fff;font:bold 12px monospace;padding:0 4px;border-radius:3px;pointer-events:none;' +
      'box-shadow:0 0 0 1px #fff;';
    cont.appendChild(b);
  });
  return true;
}
"""

JS_DESMARCAR = r"""
() => { const m = document.getElementById('__sat_marks'); if (m) m.remove(); return true; }
"""

JS_RESUMEN = r"""
() => {
  const heads = Array.from(document.querySelectorAll('h1,h2,h3'))
    .map(h => h.innerText.trim()).filter(Boolean).slice(0, 12);
  const texto = (document.body ? document.body.innerText : '')
    .replace(/\s+/g, ' ').trim().slice(0, 1200);
  return { url: location.href, title: document.title, headings: heads, texto: texto };
}
"""


def formatear(elementos: list, limite: int = 45) -> str:
    """Representación compacta para el cerebro (función pura). Muestra el href de los links."""
    if not elementos:
        return "(no se detectaron elementos accionables)"
    lineas = []
    for i, e in enumerate(elementos[:limite]):
        texto = e.get("texto", "") or "—"
        href = e.get("href")
        extra = f"  → {href[:50]}" if href else ""
        lineas.append(f"[{i}] {e.get('tipo', e.get('tag', '?'))}: {texto}{extra}")
    if len(elementos) > limite:
        lineas.append(f"… y {len(elementos) - limite} más")
    return "\n".join(lineas)