"""Een database-URL tonen zonder gebruiker en wachtwoord (brief 2026-10-23).

Een URL als `postgresql+asyncpg://gebruiker:wachtwoord@host:5432/db` hoort nooit in een `print`, een logregel of een
foutmelding: GitHub maskeert in een log alleen de VOLLEDIGE geheime waarde, niet een stuk ervan, en een logbestand
leeft langer dan het wachtwoord. Gebruik deze functie overal waar een URL getoond wordt.

De URL wordt gelezen met `sqlalchemy.engine.make_url`, dus precies zoals de applicatie hem leest: een wachtwoord met
`/` of `%`-tekens wordt niet als host uitgelegd. Zonder gebruiker, wachtwoord of queryparameters; alleen wat een mens
nodig heeft om te zien MET WELKE database er is verbonden.
"""

from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def database_url_zonder_wachtwoord(url: str | None) -> str:
    """Schema, host, poort en databasenaam van `url`; nooit gebruiker, wachtwoord of queryparameters.

    Een URL die niet te lezen is wordt NIET teruggegeven (ook niet gedeeltelijk): dan staat er `<database-url>`.
    """
    if url is None or not url.strip():
        return "<geen database-url>"
    if url.count("@") > 1:
        # Een ruwe `@` in het wachtwoord (ook als er een `?` bij staat): de URL-lezer zou het staartdeel als host tonen.
        # Dan tonen we niets; een URL met een `@` in de query valt hier ook onder, en dat is veilig.
        return "<database-url>"
    try:
        gelezen = make_url(url.strip())
    except (ArgumentError, ValueError):
        return "<database-url>"
    if gelezen.drivername.startswith("sqlite"):
        return f"{gelezen.drivername}:///{gelezen.database or ''}"
    poort = f":{gelezen.port}" if gelezen.port else ""
    return f"{gelezen.drivername}://{gelezen.host or ''}{poort}/{gelezen.database or ''}"
