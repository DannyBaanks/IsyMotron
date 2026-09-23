#!/usr/bin/env python3
"""isymotron avatar parser -- compilador texto-es -> receta (frontend del engine).

PORTADO DE ISyCo/tools/munder-cli/lib-avatar.cjs (parseAvatarDesc,
validateAvatarRecipe, compileAvatar + tablas AV_*). Misma semantica:
determinista y total, lo no reconocido cae a warnings[] (nunca se inventa
geometria), la ULTIMA mencion por categoria gana.
"""

from __future__ import annotations

import re
import unicodedata

from core.isymotron.avatar import (
    AVATAR_VOCAB,
    PORTRAIT_H,
    PORTRAIT_W,
    compose_avatar,
    encode_png,
)

AV_PIEL = {
    "clara": "light", "blanca": "light", "palida": "light",
    "morena": "tan", "bronceada": "tan", "trigueña": "tan",
    "marron": "brown", "cafe": "brown",
    "oscura": "dark", "negra": "dark", "afro": "dark",
}
AV_PELO_ESTILO = {
    "corto": "styleShort", "corta": "styleShort", "raya": "styleShort",
    "flequillo": "styleFloppy", "lacio": "styleFloppy", "lacia": "styleFloppy",
    "caido": "styleFloppy", "caida": "styleFloppy",
    "largo": "styleFrame", "larga": "styleFrame", "enmarcado": "styleFrame",
    "enmarcada": "styleFrame", "melena": "styleFrame",
    "moño": "styleBun", "recogido": "styleBun", "recogida": "styleBun", "chongo": "styleBun",
    "rizado": "styleCurly", "rizada": "styleCurly", "rizos": "styleCurly",
    "despeinado": "styleMessy", "despeinada": "styleMessy",
    "desordenado": "styleMessy", "desordenada": "styleMessy",
    "entradas": "styleRecede", "engominado": "styleRecede", "engominada": "styleRecede",
    "atras": "styleRecede",
    "pinchos": "styleSpiky", "puntiagudo": "styleSpiky", "puntiaguda": "styleSpiky",
    "punk": "styleSpiky",
    "calvo": "styleBald", "calva": "styleBald", "pelon": "styleBald",
    "pelona": "styleBald", "sin pelo": "styleBald",
}
AV_PELO_COLOR = {
    "negro": [30, 22, 18], "negra": [30, 22, 18],
    "castano": [92, 60, 34], "castaña": [92, 60, 34], "castana": [92, 60, 34],
    "marron": [110, 75, 45], "morena": [110, 75, 45],
    "rubio": [190, 158, 95], "rubia": [190, 158, 95],
    "pelirrojo": [150, 70, 40], "pelirroja": [150, 70, 40],
    "rojo": [150, 70, 40], "roja": [150, 70, 40],
    "gris": [168, 164, 154], "blanco": [228, 228, 228], "blanca": [228, 228, 228],
    "canoso": [150, 150, 150], "canosa": [150, 150, 150],
}
AV_ROPA = {
    "traje": "suit", "sastre": "suit",
    "camisa": "dressshirt", "camisa de vestir": "dressshirt",
    "polo": "polo", "playera": "polo",
    "blusa": "blouse",
    "cardigan": "cardigan", "cárdigan": "cardigan",
    "sueter": "sweater", "jersey": "sweater", "sudadera": "sweater",
}
AV_COLOR = {
    "rojo": [176, 65, 58], "roja": [176, 65, 58],
    "azul": [110, 140, 180],
    "verde": [110, 174, 111],
    "negro": [58, 58, 68], "negra": [58, 58, 68],
    "blanco": [240, 238, 234], "blanca": [240, 238, 234],
    "gris": [150, 150, 150],
    "rosa": [236, 174, 192],
    "morado": [150, 146, 170], "morada": [150, 146, 170],
    "violeta": [150, 146, 170],
    "marron": [150, 120, 86],
    "beige": [236, 220, 190],
    "amarillo": [232, 200, 90], "amarilla": [232, 200, 90],
    "naranja": [210, 130, 60],
    "celeste": [140, 190, 220],
}
AV_CEJA = {"rectas": "flat", "recta": "flat", "enojadas": "angry", "enojada": "angry",
           "arqueadas": "raised", "arqueada": "raised", "suaves": "soft", "suave": "soft"}
AV_BOCA = {"neutra": "neutral", "neutro": "neutral", "sonrisa": "smile", "sonrie": "smile",
           "sonriente": "smile", "ceño": "frown", "molesta": "frown", "molesto": "frown",
           "mueca": "grin", "sonrisota": "grin"}
AV_FACIAL = {"bigote": "mustache", "mostacho": "mustache", "bigote corto": "mustacheSm",
             "perilla": "goatee", "chivo": "goatee", "barba": "stubble",
             "incipiente": "stubble", "barba de dias": "stubble"}
AV_CORBATIN = [170, 58, 58]  # corbata por defecto (la de Michael)

AV_DEFAULT_RECIPE = {
    "skin": "light", "hairc": [74, 51, 32], "hair": "styleShort", "hairargs": {},
    "cloth": "dressshirt", "c1": [150, 150, 150], "c2": [240, 238, 234],
    "brow": "flat", "mouth": "neutral",
}


def av_norm(s) -> str:
    return unicodedata.normalize("NFD", str(s or "").lower()).encode("ascii", "ignore").decode("ascii")


def _has(phrase: str, table: dict):
    """Longest-key-first match; multi-word keys by substring, rest by word."""
    for k in sorted(table.keys(), key=len, reverse=True):
        if " " in k:
            if k in phrase:
                return k
        elif re.search(r"(^| )" + re.escape(k) + r"( |$)", phrase):
            return k
    return None


def _color_in(phrase: str):
    for k in sorted(AV_COLOR.keys(), key=len, reverse=True):
        if re.search(r"(^| )" + re.escape(k) + r"( |$)", phrase):
            return k
    return None


def parse_avatar_desc(text: str) -> dict:
    """Parse Spanish description into an engine recipe.

    Returns {"recipe", "warnings", "matched"}. Deterministic and total.
    """
    warnings: list[str] = []
    matched: list[str] = []
    recipe = {**AV_DEFAULT_RECIPE, "hairargs": {**AV_DEFAULT_RECIPE["hairargs"]}}
    phrases = [s.strip() for s in re.split(r"[,;.\n]+|\s+y\s+|\s+con\s+", av_norm(text)) if s.strip()]
    if not phrases:
        return {"recipe": recipe, "warnings": ["descripción vacía: se usó base neutra"], "matched": matched}

    last_ctx = None
    for phrase in phrases:
        hit = False
        if "piel" in phrase or "tez" in phrase or "cara" in phrase:
            k = _has(phrase, AV_PIEL)
            if k:
                recipe["skin"] = AV_PIEL[k]
                matched.append(f"piel:{k}")
                hit = True
        if "pelo" in phrase or "cabello" in phrase or "cabellera" in phrase or "afro" in phrase:
            k = _has(phrase, AV_PELO_ESTILO)
            if k:
                recipe["hair"] = AV_PELO_ESTILO[k]
                matched.append(f"pelo:{k}")
                hit = True
                last_ctx = "hair"
            elif "afro" in phrase:
                recipe["hair"] = "styleCurly"
                matched.append("pelo:afro")
                hit = True
                last_ctx = "hair"
            c = _has(phrase, AV_PELO_COLOR)
            if c:
                recipe["hairc"] = list(AV_PELO_COLOR[c])
                matched.append(f"pelo-color:{c}")
                hit = True
                last_ctx = "hair"
            if "raya" in phrase:
                if "derecha" in phrase:
                    recipe["hairargs"] = {**recipe["hairargs"], "part": "R"}
                    matched.append("raya:R")
                else:
                    recipe["hairargs"] = {**recipe["hairargs"], "part": "L"}
                    matched.append("raya:L")
                hit = True
        cloth_k = _has(phrase, AV_ROPA)
        if cloth_k:
            recipe["cloth"] = AV_ROPA[cloth_k]
            matched.append(f"ropa:{cloth_k}")
            hit = True
            last_ctx = "cloth"
            c = _color_in(phrase)
            if c:
                recipe["c1"] = list(AV_COLOR[c])
                matched.append(f"ropa-color:{c}")
        else:
            c = _color_in(phrase)
            if c and "corbata" not in phrase and "pelo" not in phrase and "cabello" not in phrase:
                recipe["c1"] = list(AV_COLOR[c])
                matched.append(f"ropa-color:{c}")
                hit = True
        if "corbata" in phrase:
            c = _color_in(phrase)
            recipe["tie"] = list(AV_COLOR[c]) if c else list(AV_CORBATIN)
            matched.append(f"corbata:{c or 'default'}")
            hit = True
        b = _has(phrase, AV_CEJA)
        if ("ceja" in phrase or b) and b:
            recipe["brow"] = AV_CEJA[b]
            matched.append(f"ceja:{b}")
            hit = True
        m = _has(phrase, AV_BOCA)
        if ("boca" in phrase or "sonrisa" in phrase or "mueca" in phrase or m) and m:
            recipe["mouth"] = AV_BOCA[m]
            matched.append(f"boca:{m}")
            hit = True
        f = _has(phrase, AV_FACIAL)
        if f:
            recipe["facial"] = AV_FACIAL[f]
            matched.append(f"facial:{f}")
            hit = True
        if "gafas" in phrase or "lentes" in phrase or "anteojos" in phrase:
            recipe["glasses"] = True
            matched.append("gafas")
            hit = True
        if "rubor" in phrase or "mejillas" in phrase or "sonroj" in phrase:
            recipe["blush"] = True
            matched.append("rubor")
            hit = True
        if "pesta" in phrase:
            recipe["lashes"] = True
            matched.append("pestañas")
            hit = True
        if "robust" in phrase or "gordo" in phrase or "corpulent" in phrase or "rechoncho" in phrase:
            recipe["heavy"] = True
            matched.append("robusto")
            hit = True
        if not hit and last_ctx:
            # Reintento con contexto: modificador huérfano ("pinchos" tras
            # "pelo negro con..."). Solo tablas de la categoría activa.
            if last_ctx == "hair":
                k = _has(phrase, AV_PELO_ESTILO)
                if k:
                    recipe["hair"] = AV_PELO_ESTILO[k]
                    matched.append(f"pelo:{k} (ctx)")
                    hit = True
                else:
                    c = _has(phrase, AV_PELO_COLOR)
                    if c:
                        recipe["hairc"] = list(AV_PELO_COLOR[c])
                        matched.append(f"pelo-color:{c} (ctx)")
                        hit = True
            elif last_ctx == "cloth":
                c = _color_in(phrase)
                if c:
                    recipe["c1"] = list(AV_COLOR[c])
                    matched.append(f"ropa-color:{c} (ctx)")
                    hit = True
        if not hit:
            warnings.append(f'no entendí: "{phrase.strip()}"')
    return {"recipe": recipe, "warnings": warnings, "matched": matched}


def validate_avatar_recipe(recipe: dict, vocab: dict | None = None) -> list[str]:
    """Validate a recipe against the engine vocabulary. Pure."""
    errs: list[str] = []
    if not recipe or not isinstance(recipe, dict):
        return ["receta ausente"]
    V = vocab or {}

    def check(field: str, lst, label: str | None = None) -> None:
        if recipe.get(field) is None:
            return
        if not isinstance(lst, list) or recipe[field] not in lst:
            errs.append(f"{label or field} '{recipe[field]}' fuera de vocabulario")

    check("skin", (V or {}).get("skins"), "piel")
    check("hair", (V or {}).get("hairs"), "pelo")
    check("cloth", (V or {}).get("cloths"), "ropa")
    if recipe.get("facial") is not None:
        check("facial", (V or {}).get("facials"), "facial")
    if recipe.get("brow") is not None:
        check("brow", (V or {}).get("brows"), "ceja")
    if recipe.get("mouth") is not None:
        check("mouth", (V or {}).get("mouths"), "boca")

    def rgb(v, label: str) -> None:
        if v is None:
            return
        if (not isinstance(v, list) or len(v) != 3
                or any(not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > 255 for n in v)):
            errs.append(f"{label} RGB inválido")

    rgb(recipe.get("hairc"), "pelo-color")
    rgb(recipe.get("c1"), "ropa-color")
    rgb(recipe.get("c2"), "ropa-color-sec")
    if recipe.get("tie") is not None:
        rgb(recipe.get("tie"), "corbata")
    return errs


def compile_avatar(text: str) -> dict:
    """Compile Spanish text -> PNG via the engine.

    Returns {"png","recipe","warnings","matched","w","h"}. Raises on invalid
    recipe (programmer error, never user error: the parser only emits vocab).
    """
    parsed = parse_avatar_desc(text)
    errs = validate_avatar_recipe(parsed["recipe"], AVATAR_VOCAB)
    if errs:
        raise ValueError(f"receta inválida: {'; '.join(errs)}")
    buf = compose_avatar(parsed["recipe"])
    if not isinstance(buf, list) or len(buf) != PORTRAIT_W * PORTRAIT_H * 4:
        raise RuntimeError("el engine devolvió un buffer inesperado")
    return {
        "png": encode_png(PORTRAIT_W, PORTRAIT_H, buf),
        "recipe": parsed["recipe"],
        "warnings": parsed["warnings"],
        "matched": parsed["matched"],
        "w": PORTRAIT_W,
        "h": PORTRAIT_H,
    }
