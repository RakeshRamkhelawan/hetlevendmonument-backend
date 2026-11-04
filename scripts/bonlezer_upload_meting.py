"""Upload de 24 testbonnen via de API en tel de uitslag per veld (bonlezer dag 3).

Draait IN de API-container van `scripts/bonlezer/meet_upload.sh` en praat met het meetharnas
(`scripts/bonlezer_upload_api.py`) over echte HTTP. Per document: `POST /api/v1/bonnen`, dan
`GET /api/v1/bonnen/{id}` tot de worker klaar is, daarna scoren met de telregels van dag 1.

Daarnaast, om te zien dat de randen dicht zijn (elke uitslag wordt letterlijk afgedrukt):

- tenant B vraagt de bon van tenant A op -> 404;
- een bestand van 26 MB en een `.exe` -> geweigerd, en de uploadmap groeit niet;
- zes uploads kort na elkaar -> de zesde geeft 429 met een Nederlandse melding.

Gebruik: `PYTHONPATH=/app:/repo/scripts python /repo/scripts/bonlezer_upload_meting.py --uit /uit/upload-verslag.md`
"""

from __future__ import annotations

import argparse
import json
import secrets
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from bonlezer_worker_meting import als_velden

from src.core.als.bonlezer.meting import (
    VELDEN,
    DocumentUitslag,
    beoordeel,
    onverwachte_tarieven,
    tel,
)

SET = Path("/repo/tests/fixtures/bonnen")
UPLOADS = Path("/data/bonnen")
BASIS = "http://127.0.0.1:8000/api/v1/bonnen"
WACHT_SECONDEN = 300
PAUZE_SECONDEN = 6.0
RANDEN_TENANT = 5


def _vraag(
    methode: str, url: str, tenant: int, body: bytes | None = None, grens: str | None = None
) -> tuple[int, dict[str, object]]:
    headers = {"X-Test-Tenant": str(tenant)}
    if grens:
        headers["Content-Type"] = f"multipart/form-data; boundary={grens}"
    verzoek = urllib.request.Request(url, data=body, method=methode, headers=headers)
    try:
        with urllib.request.urlopen(verzoek, timeout=60) as antwoord:
            return antwoord.status, json.loads(antwoord.read())
    except urllib.error.HTTPError as fout:
        tekst = fout.read().decode("utf-8", "replace")
        try:
            return fout.code, json.loads(tekst)
        except ValueError:
            return fout.code, {"tekst": tekst[:200]}


def upload(tenant: int, naam: str, inhoud: bytes) -> tuple[int, dict[str, object]]:
    grens = "----bl3" + secrets.token_hex(8)
    kop = (
        f'--{grens}\r\nContent-Disposition: form-data; name="file"; filename="{naam}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body = kop + inhoud + f"\r\n--{grens}--\r\n".encode()
    return _vraag("POST", BASIS, tenant, body, grens)


def wacht_op_uitkomst(tenant: int, bestand_id: str) -> dict[str, object]:
    eind = time.monotonic() + WACHT_SECONDEN
    while time.monotonic() < eind:
        _, antwoord = _vraag("GET", f"{BASIS}/{bestand_id}", tenant)
        data = antwoord["data"]
        assert isinstance(data, dict)
        if data["status"] != "wachten":
            return data
        time.sleep(0.5)
    raise TimeoutError(bestand_id)


def aantal_bestanden() -> int:
    return sum(1 for p in UPLOADS.rglob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="Meet de bonlezer via de API")
    parser.add_argument("--uit", type=Path, required=True)
    argumenten = parser.parse_args()

    uitslagen: list[DocumentUitslag] = []
    fouten: list[str] = []
    tijden: list[float] = []
    eerste: tuple[str, str] | None = None
    vorige_start = time.perf_counter() - PAUZE_SECONDEN
    for antwoorden_pad in sorted(SET.glob("*.json")):
        naam = antwoorden_pad.stem
        antwoorden = json.loads(antwoorden_pad.read_text(encoding="utf-8"))
        bestand = next(p for p in (SET / f"{naam}.pdf", SET / f"{naam}.jpg") if p.exists())
        # Hoogstens 10 uploads per minuut: de route begrenst een gebruiker op 12 per minuut.
        wacht = PAUZE_SECONDEN - (time.perf_counter() - vorige_start)
        if wacht > 0:
            time.sleep(wacht)
        start = vorige_start = time.perf_counter()
        code, antwoord = upload(1, bestand.name, bestand.read_bytes())
        assert code == 201, (code, antwoord)
        data = antwoord["data"]
        assert isinstance(data, dict), antwoord
        bestand_id = str(data["bestand_id"])
        if eerste is None:
            eerste = (naam, bestand_id)
        uitkomst = wacht_op_uitkomst(1, bestand_id)
        tijden.append(time.perf_counter() - start)
        print(f"{naam}: POST {code} -> {uitkomst['status']} in {tijden[-1]:.1f} s", flush=True)
        if uitkomst["status"] != "gelezen":
            fouten.append(f"{naam}: {uitkomst['status']} ({uitkomst.get('reden', '')})")
            continue
        velden = als_velden(uitkomst)
        uitslagen.append(
            DocumentUitslag(
                naam,
                str(antwoorden["soort"]),
                beoordeel(velden, antwoorden),
                onverwachte_tarieven(velden, antwoorden),
            )
        )

    assert eerste is not None
    randen: list[str] = []
    code, antwoord = _vraag("GET", f"{BASIS}/{eerste[1]}", 2)
    randen.append(
        f"| tenant B vraagt de bon van tenant A op | {code} | {json.dumps(antwoord)[:120]} |"
    )

    voor = aantal_bestanden()
    code, antwoord = upload(RANDEN_TENANT, "groot.pdf", b"%PDF-1.4\n" + b"0" * 26_000_000)
    randen.append(f"| bestand van 26 MB | {code} | {json.dumps(antwoord)[:120]} |")
    code, antwoord = upload(RANDEN_TENANT, "bon.exe", b"%PDF-1.4\n" + b"x" * 100)
    randen.append(
        f"| bestand van het verkeerde soort (.exe) | {code} | {json.dumps(antwoord)[:120]} |"
    )
    randen.append(
        f"| bestanden in de uploadmap voor en na de twee weigeringen | {voor} -> {aantal_bestanden()} | |"
    )

    klein = SET / f"{eerste[0]}.pdf"
    if not klein.exists():
        klein = SET / f"{eerste[0]}.jpg"
    ids = []
    for volgnummer in range(1, 7):
        code, antwoord = upload(3, klein.name, klein.read_bytes())
        randen.append(
            f"| upload {volgnummer} van tenant 3 achter elkaar | {code} | {json.dumps(antwoord)[:140]} |"
        )
        data = antwoord.get("data")
        if code == 201 and isinstance(data, dict):
            ids.append(str(data["bestand_id"]))
    for bestand_id in ids:
        wacht_op_uitkomst(3, bestand_id)

    geteld = tel(uitslagen)
    regels = [
        f"# Meting bonlezer dag 3 via de API, {date.today().isoformat()}",
        "",
        f"- Documenten via POST en GET gelezen: {len(uitslagen)} van 24",
        f"- Tijd per document (upload tot uitkomst): gemiddeld {sum(tijden) / len(tijden):.1f} s, "
        f"langste {max(tijden):.1f} s",
        "",
        "| Veld | via de API (regels) |",
        "| --- | --- |",
    ]
    for veld in VELDEN:
        goed, totaal = geteld[veld]
        procent = f" ({100 * goed // totaal}%)" if totaal else ""
        regels.append(f"| {veld} | {goed}/{totaal}{procent} |")
    regels += ["", "## Niet gelezen", "", *(fouten or ["Geen."])]
    regels += [
        "",
        "## Randen",
        "",
        "| Wat | Antwoord | Inhoud |",
        "| --- | --- | --- |",
        *randen,
        "",
    ]
    tekst = "\n".join(regels)
    print(tekst)
    argumenten.uit.write_text(tekst, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
