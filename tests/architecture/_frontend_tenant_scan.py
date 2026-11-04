"""Structuurscanner voor frontend-bron: vindt objectliteralen met de sleutel tenant_id/tenantId.

Pure Python, bewust: de CI-job die tests/architecture draait heeft geen frontend/node_modules,
dus een TypeScript-parser is daar niet beschikbaar. In plaats van een substring zoekt dit
op STRUCTUUR: eerst tokens (zonder comments en zonder stringinhoud), dan per accolade de
soort (objectliteraal, type, blok, destructuring), en pas dan de sleutels die DIRECT in een
objectliteraal staan.

Bekende grens (de bewaker meet dit niet): een regex-literaal met een aanhalingsteken erin
kan de tokenizer ontregelen. `tokens_zijn_in_balans` is de meting die dat zichtbaar maakt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SLEUTELS = frozenset({"tenant_id", "tenantId"})
# Aanroepen die een payload naar de API sturen. `mutate`/`mutateAsync` zijn React Query-
# mutaties: hun argument wordt de body van de mutationFn.
SEND_METHODES = frozenset({"get", "post", "put", "patch", "delete", "request"})
SEND_ONTVANGERS = frozenset({"api", "apiClient", "axios", "http", "httpClient", "client"})
SEND_FUNCTIES = frozenset({"fetch", "mutate", "mutateAsync", "URLSearchParams"})
# Containers waarvan `.append(sleutel, ..)` / `.set(sleutel, ..)` een queryparameter of formulierveld
# vult dat naar de API gaat. Een `Map.set('tenant_id', ..)` is geen verzending en telt niet mee.
PARAM_CONTAINERS = frozenset({"URLSearchParams", "FormData"})
PARAM_METHODES = frozenset({"append", "set"})

_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_SPATIES = " \t\r\n"
# Na deze tokens is een `/` het begin van een regex en geen deling; we slaan regexen over
# zodat een aanhalingsteken erin de tokenizer niet ontregelt.
_VOOR_REGEX = frozenset(
    {"(", ",", "=", ":", "[", "!", "&", "|", "?", "{", ";", "return", "=>"}
)
_NA_IDENT_GEEN_OBJECT = frozenset(
    {"return", "yield", "await", "typeof", "in", "of", "case", "throw", "new"}
)


@dataclass(frozen=True)
class Token:
    soort: str  # ident | str | punct
    tekst: str
    regel: int


@dataclass(frozen=True)
class Treffer:
    regel: int
    functie: str
    sleutel: str
    aanroep: str


def tokenize(bron: str) -> list[Token]:
    tokens: list[Token] = []
    i, n, regel = 0, len(bron), 1
    while i < n:
        c = bron[i]
        if c == "\n":
            regel += 1
            i += 1
        elif c in _SPATIES:
            i += 1
        elif bron.startswith("//", i):
            j = bron.find("\n", i)
            i = n if j == -1 else j
        elif bron.startswith("/*", i):
            j = bron.find("*/", i + 2)
            j = n if j == -1 else j + 2
            regel += bron.count("\n", i, j)
            i = j
        elif c in "'\"":
            j = i + 1
            while j < n and bron[j] != c and bron[j] != "\n":
                j += 2 if bron[j] == "\\" else 1
            if j >= n or bron[j] != c:
                i += 1  # apostrof in JSX-tekst ("don't"): geen string, de rest blijft code
                continue
            tokens.append(Token("str", bron[i + 1 : j], regel))
            i = j + 1
        elif c == "`":
            j, diepte = i + 1, 0
            while j < n:
                if bron[j] == "\\":
                    j += 2
                    continue
                if bron.startswith("${", j):
                    diepte += 1
                    j += 2
                    continue
                if bron[j] == "}" and diepte:
                    diepte -= 1
                elif bron[j] == "`" and not diepte:
                    break
                j += 1
            tokens.append(Token("str", "", regel))
            regel += bron.count("\n", i, j)
            i = j + 1
        elif c == "/" and not bron.startswith("/>", i) and (not tokens or tokens[-1].tekst in _VOOR_REGEX):
            j = i + 1
            in_klasse = False
            while j < n and bron[j] != "\n":
                if bron[j] == "\\":
                    j += 2
                    continue
                if bron[j] == "[":
                    in_klasse = True
                elif bron[j] == "]":
                    in_klasse = False
                elif bron[j] == "/" and not in_klasse:
                    break
                j += 1
            if j >= n or bron[j] != "/":
                tokens.append(Token("punct", c, regel))  # JSX-tekst als "(/hitl)": geen regex
                i += 1
                continue
            tokens.append(Token("str", "", regel))
            i = j + 1
        else:
            m = _IDENT.match(bron, i)
            if m:
                tokens.append(Token("ident", m.group(), regel))
                i = m.end()
            elif bron.startswith(("...", "=>", "?."), i):
                lengte = 3 if bron.startswith("...", i) else 2
                tokens.append(Token("punct", bron[i : i + lengte], regel))
                i += lengte
            else:
                tokens.append(Token("punct", c, regel))
                i += 1
    return tokens


def tokens_zijn_in_balans(tokens: list[Token]) -> bool:
    diepte = {"{": 0, "(": 0, "[": 0}
    sluit = {"}": "{", ")": "(", "]": "["}
    for t in tokens:
        if t.soort != "punct":
            continue
        if t.tekst in diepte:
            diepte[t.tekst] += 1
        elif t.tekst in sluit:
            diepte[sluit[t.tekst]] -= 1
            if diepte[sluit[t.tekst]] < 0:
                return False
    return not any(diepte.values())


def _open_bij(tokens: list[Token], sluit_index: int) -> int:
    sluit = tokens[sluit_index].tekst
    open_ = {")": "(", "]": "[", "}": "{"}[sluit]
    diepte = 0
    for k in range(sluit_index, -1, -1):
        t = tokens[k]
        if t.soort != "punct":
            continue
        if t.tekst == sluit:
            diepte += 1
        elif t.tekst == open_:
            diepte -= 1
            if diepte == 0:
                return k
    return -1


def _sluit_bij(tokens: list[Token], open_index: int) -> int:
    diepte = 0
    for k in range(open_index, len(tokens)):
        t = tokens[k]
        if t.soort != "punct":
            continue
        if t.tekst == "{":
            diepte += 1
        elif t.tekst == "}":
            diepte -= 1
            if diepte == 0:
                return k
    return -1


def _functienaam(tokens: list[Token], open_haakje: int) -> str:
    """Naam bij een parameterlijst die op `open_haakje` begint; `<anon>` als er geen is."""
    k = open_haakje - 1
    if k >= 0 and tokens[k].tekst == ">":  # generieke parameters: naam<T>(...)
        diepte = 0
        while k >= 0:
            if tokens[k].tekst == ">":
                diepte += 1
            elif tokens[k].tekst == "<":
                diepte -= 1
                if diepte == 0:
                    k -= 1
                    break
            k -= 1
    if k >= 0 and tokens[k].tekst == "async":
        k -= 1
    elif k >= 1 and tokens[k].tekst == "function":
        return "<anon>"
    if k >= 1 and tokens[k].tekst == ":" and tokens[k - 1].soort in ("ident", "str"):
        return tokens[k - 1].tekst  # { naam: async (..) => {
    if k >= 0 and tokens[k].soort == "ident" and tokens[k].tekst not in ("function", "async"):
        return tokens[k].tekst
    if k >= 0 and tokens[k].tekst in ("=", ">"):
        for m in range(k - 1, max(k - 40, -1), -1):
            if tokens[m].tekst in ("const", "let", "var") and m + 1 < len(tokens):
                return tokens[m + 1].tekst
    return "<anon>"


def _open_voor_returntype(tokens: list[Token], i: int) -> int:
    """Index van de `(` van de parameterlijst als tokens[i] een lichaam na `): Type` opent."""
    diepte = 0
    for k in range(i - 1, max(i - 60, 0), -1):
        t = tokens[k]
        if t.soort != "punct":
            continue
        if t.tekst in (">", "]", "}"):
            diepte += 1
        elif t.tekst in ("<", "[", "{"):
            diepte -= 1
            if diepte < 0:
                return -1
        elif t.tekst in (";", "=", "(", ")") and diepte == 0 and not (t.tekst == ")" and tokens[k + 1].tekst == ":"):
            return -1
        elif t.tekst == ":" and diepte == 0 and tokens[k - 1].tekst == ")":
            return _open_bij(tokens, k - 1)
    return -1


def _soort_accolade(tokens: list[Token], i: int, ouder: str | None) -> tuple[str, str | None]:
    """(soort, functienaam). soort: object | type | blok | patroon | klasse."""
    if i == 0:
        return "blok", None
    vorige = tokens[i - 1]
    p = vorige.tekst
    # interface X {  /  interface X extends Y {  /  type X = {  /  class X {
    for k in range(i - 1, max(i - 12, -1), -1):
        if tokens[k].soort == "punct" and tokens[k].tekst in (";", "{", "}", "("):
            break
        if tokens[k].tekst in ("interface", "enum", "namespace"):
            return "type", None
        if tokens[k].tekst == "class":
            return "klasse", None
        if tokens[k].tekst == "type" and k + 2 < i and tokens[k + 2].tekst in ("=", "<"):
            return "type", None
    if p in ("const", "let", "var"):
        return "patroon", None
    if p in (">", "]") or (vorige.soort == "ident" and p not in _NA_IDENT_GEEN_OBJECT):
        # `function f(...): Promise<X> {`: de `{` opent een functielichaam met een returntype.
        o = _open_voor_returntype(tokens, i)
        if o >= 0:
            return "blok", _functienaam(tokens, o)
    if p == ")":
        o = _open_bij(tokens, i - 1)
        return "blok", _functienaam(tokens, o) if o >= 0 else None
    if p == "=>":
        # `=> {` is een functielichaam; de parameterlijst staat links van de pijl.
        if i >= 2 and tokens[i - 2].tekst == ")":
            o = _open_bij(tokens, i - 2)
            return "blok", _functienaam(tokens, o) if o >= 0 else None
        return "blok", None
    if p == ":":
        # `a: {` in een objectliteraal is een geneste literaal; elders een typeannotatie.
        return ("object", None) if ouder == "object" else ("type", None)
    if p in ("<", "|", "&", "extends", "as", "satisfies"):
        return "type", None
    if vorige.soort == "ident" and p not in _NA_IDENT_GEEN_OBJECT:
        return "blok", None  # else {, try {, naam {, ...
    if p in (";", "}", "{"):
        return "blok", None
    return "object", None


def _sleutels_in_objecten(tokens: list[Token]) -> list[tuple[int, Treffer]]:
    """Alle plekken waar tenant_id/tenantId een SLEUTEL is in een objectliteraal."""
    treffers: list[tuple[int, Treffer]] = []
    stapel: list[tuple[str, str | None]] = []  # (soort, functienaam)
    for i, t in enumerate(tokens):
        if t.soort == "punct" and t.tekst == "{":
            ouder = stapel[-1][0] if stapel else None
            stapel.append(_soort_accolade(tokens, i, ouder))
            continue
        if t.soort == "punct" and t.tekst == "}":
            if stapel:
                stapel.pop()
            continue
        if not stapel or stapel[-1][0] != "object":
            continue
        if t.tekst not in SLEUTELS or t.soort not in ("ident", "str"):
            continue
        vorige = tokens[i - 1].tekst if i else ""
        volgende = tokens[i + 1].tekst if i + 1 < len(tokens) else ""
        if vorige not in ("{", ","):
            continue  # `x.tenantId`, `...tenantId`: een lezing, geen sleutel
        if volgende == ":":
            pass
        elif t.soort == "ident" and volgende in (",", "}"):
            # Shorthand `{ tenantId }` is in een literaal een sleutel; als patroon (links van
            # een `=` of `=>`, of voor een typeannotatie) is het een lezing.
            sluit = _sluit_bij(tokens, _open_bij_object(tokens, i))
            na = tokens[sluit + 1].tekst if 0 <= sluit + 1 < len(tokens) else ""
            if na in ("=", "=>", ":"):
                continue
        else:
            continue
        functie = next((f for s, f in reversed(stapel) if s == "blok" and f and f != "<anon>"), "<module>")
        treffers.append((i, Treffer(t.regel, functie, t.tekst, "")))
    return treffers


def _sluit_haakje(tokens: list[Token], open_index: int) -> int:
    diepte = 0
    for k in range(open_index, len(tokens)):
        t = tokens[k]
        if t.soort != "punct":
            continue
        if t.tekst == "(":
            diepte += 1
        elif t.tekst == ")":
            diepte -= 1
            if diepte == 0:
                return k
    return -1


def _sendpunten(tokens: list[Token]) -> list[tuple[int, int, str]]:
    """(open_index, sluit_index, naam) van elke aanroep die naar de API stuurt."""
    punten: list[tuple[int, int, str]] = []
    for i, t in enumerate(tokens):
        if t.soort != "punct" or t.tekst != "(" or i == 0:
            continue
        k = i - 1
        if tokens[k].tekst == ">":  # post<Antwoord>(...)
            diepte = 0
            while k >= 0:
                if tokens[k].tekst == ">":
                    diepte += 1
                elif tokens[k].tekst == "<":
                    diepte -= 1
                    if diepte == 0:
                        k -= 1
                        break
                k -= 1
        if k < 0 or tokens[k].soort != "ident":
            continue
        naam = tokens[k].tekst
        if naam in SEND_FUNCTIES:
            pass
        elif (
            naam in SEND_METHODES
            and k >= 2
            and tokens[k - 1].tekst in (".", "?.")
            and tokens[k - 2].tekst in SEND_ONTVANGERS
        ):
            naam = f"{tokens[k - 2].tekst}.{naam}"
        else:
            continue
        sluit = _sluit_haakje(tokens, i)
        if sluit > i:
            punten.append((i, sluit, naam))
    return punten


def _param_variabelen(tokens: list[Token]) -> set[str]:
    """Namen van variabelen die met `= new URLSearchParams(..)` of `= new FormData(..)` zijn gemaakt."""
    namen: set[str] = set()
    for i in range(len(tokens) - 3):
        if (
            tokens[i].soort == "ident"
            and tokens[i + 1].tekst == "="
            and tokens[i + 2].tekst == "new"
            and tokens[i + 3].tekst in PARAM_CONTAINERS
        ):
            namen.add(tokens[i].tekst)
    return namen


def _functie_bij(tokens: list[Token], doel: int) -> str:
    """De omsluitende functie van token `doel` (zelfde accoladetelling als de objectscan)."""
    stapel: list[tuple[str, str | None]] = []
    for i, t in enumerate(tokens[:doel]):
        if t.soort == "punct" and t.tekst == "{":
            stapel.append(_soort_accolade(tokens, i, stapel[-1][0] if stapel else None))
        elif t.soort == "punct" and t.tekst == "}" and stapel:
            stapel.pop()
    return next((f for s, f in reversed(stapel) if s == "blok" and f and f != "<anon>"), "<module>")


def _param_treffers(tokens: list[Token]) -> list[Treffer]:
    """`params.append('tenant_id', ..)` / `.set(..)` op een URLSearchParams of FormData."""
    variabelen = _param_variabelen(tokens)
    treffers: list[Treffer] = []
    for i in range(2, len(tokens) - 2):
        if tokens[i].tekst not in PARAM_METHODES or tokens[i - 1].tekst not in (".", "?."):
            continue
        if tokens[i + 1].tekst != "(" or tokens[i + 2].soort != "str":
            continue
        if tokens[i + 2].tekst not in SLEUTELS:
            continue
        ontvanger = tokens[i - 2]
        # `x.append(..)` met x gemaakt via new URLSearchParams/FormData, of direct
        # `new URLSearchParams().append(..)` (de ontvanger is dan de sluitende `)`).
        direct = ontvanger.tekst == ")" and _is_nieuwe_container(tokens, i - 2)
        if ontvanger.tekst in variabelen or direct:
            treffers.append(
                Treffer(tokens[i + 2].regel, _functie_bij(tokens, i), tokens[i + 2].tekst, f"{ontvanger.tekst}.{tokens[i].tekst}")
            )
    return treffers


def _is_nieuwe_container(tokens: list[Token], sluit_index: int) -> bool:
    o = _open_bij(tokens, sluit_index)
    return o >= 2 and tokens[o - 1].tekst in PARAM_CONTAINERS and tokens[o - 2].tekst == "new"


def vind_treffers(bron: str) -> list[Treffer]:
    """tenant_id/tenantId als sleutel in een objectliteraal BINNEN een aanroep die naar de API
    stuurt (body, `params`, `JSON.stringify({...})`, mutatiepayload, `new URLSearchParams({..})`),
    en als sleutel van `.append`/`.set` op een URLSearchParams of FormData."""
    tokens = tokenize(bron)
    punten = _sendpunten(tokens)
    treffers: list[Treffer] = []
    for index, t in _sleutels_in_objecten(tokens):
        binnen = [(o, naam) for o, s, naam in punten if o < index < s]
        if binnen:
            treffers.append(Treffer(t.regel, t.functie, t.sleutel, binnen[-1][1]))
    treffers.extend(_param_treffers(tokens))
    return treffers


def _open_bij_object(tokens: list[Token], i: int) -> int:
    """Index van de `{` die het object om token i opent."""
    diepte = 0
    for k in range(i, -1, -1):
        t = tokens[k]
        if t.soort != "punct":
            continue
        if t.tekst == "}":
            diepte += 1
        elif t.tekst == "{":
            if diepte == 0:
                return k
            diepte -= 1
    return -1
