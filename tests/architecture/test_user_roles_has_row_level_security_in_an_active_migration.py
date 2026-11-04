"""`user_roles` hoort in een ACTIEVE migratie RLS aan te hebben en een policy te krijgen (OP-190).

`user_roles` is een kale koppeltabel zonder `tenant_id`. `20260915_rls_resterende_tabellen.py`
zegt het zelf: de tabel "kan dus zelf geen policy krijgen". Variant A uit de brief geeft hem
er toch een, die BEIDE kanten toetst (gebruiker via `users`, rol via `roles`). Deze guard
bewaakt dat die twee dingen in de actieve migratieketen staan, en niet alleen in een docstring.

**Wat er getoetst wordt: STRUCTUUR, geen tekst.** Elk migratiebestand in
`src/alembic/versions/` wordt met `ast` geparsed. Alleen SQL die als argument van een
`.execute(...)`-aanroep wordt meegegeven telt, en alleen buiten `downgrade()`. Docstrings
(module en functie) en `#`-commentaar komen daardoor nooit in beeld; SQL-commentaar (`--`,
`/* */`) wordt uit de SQL gehaald voor er gezocht wordt. Een tabelnaam die in een f-string
als `{tabel}` staat, wordt opgelost naar de waarden die de omsluitende `for`-lus doorloopt of
die een hulpfunctie als argument krijgt -- het idioom van `20260915_rls_resterende_tabellen.py`.
Een lijst waar `user_roles` NIET in staat, dekt hem dus niet.

**Bewaakte elementen (twee) en wat er per element bewezen is.** De map `alembic/` in de root
is de legacy-map en wordt NIET gelezen; dat is zelf een derde bewaakte grens.

1. `ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY`
2. `CREATE POLICY <naam> ON user_roles`

**Mutatiebewijs (2026-10-04), een regel per element, in beide richtingen.** Elke mutatie is
een tijdelijk bestand in `tmp_path` met een kopie van het echte `src/alembic/versions/`
ernaast; de echte boom is niet aangeraakt en er is niets teruggezet (kopie als terugweg).
De mutanten staan als `MUTANTEN` hieronder en worden door twee geparametriseerde tests
(een per element) doorlopen, dus elke regel is een testcase met een eigen naam:

| Mutatie | Element 1 (ENABLE) | Element 2 (POLICY) |
| --- | --- | --- |
| beide statements direct in `upgrade()` | gevonden | gevonden |
| beide in een `sa.text(...)` en met `+` aaneengeschreven | gevonden | gevonden |
| de lus-opzet van 20260915 met `user_roles` in de tuple | gevonden | gevonden |
| dezelfde lus, tuple ZONDER `user_roles` | niet | niet |
| hulpfunctie, aangeroepen met `"user_roles"` | gevonden | gevonden |
| hulpfunctie, aangeroepen met een andere tabel | niet | niet |
| alleen in de moduledocstring | niet | niet |
| alleen in de docstring van `upgrade()` | niet | niet |
| alleen in een `#`-commentaar | niet | niet |
| alleen in SQL-commentaar (`--`) binnen een statement | niet | niet |
| alleen in `downgrade()` | niet | niet |
| andere tabel (`user_roles_audit`, `roles`) | niet | niet |
| alleen ENABLE, geen policy | gevonden | niet |
| alleen policy, geen ENABLE | niet | gevonden |
| `DISABLE ROW LEVEL SECURITY` in plaats van ENABLE | niet | n.v.t. |
| legacy-map `alembic/versions/` met beide | niet | niet |
| beide, in de actieve map `src/alembic/versions/` | gevonden | gevonden |
| kopie van de echte keten + een correcte migratie erbij | gevonden | gevonden |

Daarnaast is de GUARD zelf gemuteerd (door de functie in een scriptje te vervangen, niet in
het bestand): het SQL-commentaar niet meer strippen -> mutant `alleen-in-sql-commentaar` ROOD;
`downgrade()` niet meer overslaan -> `alleen-in-downgrade` ROOD; de lus-waarden negeren ->
`lus-met-user-roles-in-de-tuple` ROOD. Elk mechanisme in de guard heeft dus een mutant die hem
betrapt.

De rij "kopie van de echte keten" is de legitiem-lijkende kant in de echte context: zonder die
helft is "weiger altijd" een geldige guard. En `roles` wordt in de echte boom wel gevonden
(`test_the_analysis_finds_roles_in_the_real_chain`), zodat de parser aantoonbaar iets leest.

**Wat deze guard NIET zegt.** Hij toetst dat de statements ERIN staan, niet dat de policy
beide kanten toetst (USING op `users` en `roles`) en niet dat een LATERE migratie hem weer
uitzet. Het gedrag wordt gemeten door
`tests/integration/security/test_user_roles_is_confined_to_its_tenant.py`. Een
`RAISE`/`EXECUTE`-tekst met de statement erin telt als statement: in een DO-blok is dat
precies hoe het geschreven wordt, en het is niet te onderscheiden van een echte.
"""

from __future__ import annotations

import ast
import re
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TABEL = "user_roles"

# De ENIGE map die telt. De legacy-map `alembic/` in de root wordt bewust nooit gelezen.
_ACTIEVE_MAP = Path("src") / "alembic" / "versions"

_PLAATSHOUDER = "\x00"


@dataclass
class Dekking:
    """Welke migratiebestanden een tabel dekken, per element."""

    enable: list[str] = field(default_factory=list)
    policy: list[str] = field(default_factory=list)


def _sql_sjabloon(node: ast.AST) -> str | None:
    """De SQL van een execute-argument, met `\\x00naam\\x00` voor elke `{naam}`.

    Herkent een letterlijke string, een f-string, aaneenschrijven met `+` en een
    `sa.text(...)`/`text(...)`-omhulsel. Alles anders is `None` (wordt overgeslagen).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        delen: list[str] = []
        for deel in node.values:
            if isinstance(deel, ast.Constant) and isinstance(deel.value, str):
                delen.append(deel.value)
            elif isinstance(deel, ast.FormattedValue):
                waarde = deel.value
                naam = waarde.id if isinstance(waarde, ast.Name) else ""
                delen.append(f"{_PLAATSHOUDER}{naam}{_PLAATSHOUDER}")
        return "".join(delen)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        links, rechts = _sql_sjabloon(node.left), _sql_sjabloon(node.right)
        return None if links is None or rechts is None else links + rechts
    if isinstance(node, ast.Call) and node.args:
        functie = node.func
        is_text = (isinstance(functie, ast.Name) and functie.id == "text") or (
            isinstance(functie, ast.Attribute) and functie.attr == "text"
        )
        if is_text:
            return _sql_sjabloon(node.args[0])
    return None


def _strip_sql_commentaar(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def _tekstwaarden(node: ast.AST) -> set[str]:
    return {
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def _module_constanten(tree: ast.Module) -> dict[str, set[str]]:
    """Naam -> alle tekstwaarden in een module-level toewijzing (tuples, lijsten, strings)."""
    uit: dict[str, set[str]] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            namen = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            namen = [stmt.target.id]
        else:
            continue
        if stmt.value is None:
            continue
        for naam in namen:
            uit.setdefault(naam, set()).update(_tekstwaarden(stmt.value))
    return uit


class _Aanroepen(ast.NodeVisitor):
    """Welke tekstargumenten krijgt een hulpfunctie, buiten `downgrade()`."""

    def __init__(self) -> None:
        self.per_functie: dict[str, dict[int | str, set[str]]] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name != "downgrade":
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            doel = self.per_functie.setdefault(node.func.id, {})
            for i, arg in enumerate(node.args):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    doel.setdefault(i, set()).add(arg.value)
            for kw in node.keywords:
                if (
                    kw.arg
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    doel.setdefault(kw.arg, set()).add(kw.value.value)
        self.generic_visit(node)


class _Zoeker(ast.NodeVisitor):
    """Verzamelt de SQL-sjablonen van `.execute(...)` buiten `downgrade()`.

    Houdt per sjabloon bij welke plaatshouders een LUSVARIABELE of een FUNCTIEPARAMETER zijn
    en welke waarden die kunnen aannemen.
    """

    def __init__(self, constanten: dict[str, set[str]], aanroepen: _Aanroepen) -> None:
        self._constanten = constanten
        self._aanroepen = aanroepen
        self._bereik: list[dict[str, set[str]]] = []
        self.sjablonen: list[tuple[str, dict[str, set[str]]]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == "downgrade":
            return
        gegeven = self._aanroepen.per_functie.get(node.name, {})
        params: dict[str, set[str]] = {}
        for i, arg in enumerate(node.args.args):
            params[arg.arg] = set(gegeven.get(i, set())) | set(gegeven.get(arg.arg, set()))
        self._bereik.append(params)
        self.generic_visit(node)
        self._bereik.pop()

    def visit_For(self, node: ast.For) -> None:
        namen = {n.id for n in ast.walk(node.target) if isinstance(n, ast.Name)}
        waarden = _tekstwaarden(node.iter)
        for n in ast.walk(node.iter):
            if isinstance(n, ast.Name):
                waarden |= self._constanten.get(n.id, set())
        self._bereik.append({naam: set(waarden) for naam in namen})
        self.generic_visit(node)
        self._bereik.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "execute" and node.args:
            sjabloon = _sql_sjabloon(node.args[0])
            if sjabloon is not None:
                samen: dict[str, set[str]] = {}
                for laag in self._bereik:
                    for naam, waarden in laag.items():
                        samen[naam] = waarden
                self.sjablonen.append((sjabloon, samen))
        self.generic_visit(node)


def _uitwerkingen(sjabloon: str, variabelen: dict[str, set[str]]) -> list[str]:
    """Alle SQL-teksten die dit sjabloon kan opleveren voor de bekende lus-/parameterwaarden."""
    namen = set(re.findall(f"{_PLAATSHOUDER}(\\w*){_PLAATSHOUDER}", sjabloon))
    bekend = {n for n in namen if variabelen.get(n)}
    kandidaten = sorted(set().union(*(variabelen[n] for n in bekend))) if bekend else [""]
    uit: list[str] = []
    for kandidaat in kandidaten:
        tekst = sjabloon
        for naam in namen:
            vervanging = kandidaat if naam in bekend else "X"
            tekst = tekst.replace(f"{_PLAATSHOUDER}{naam}{_PLAATSHOUDER}", vervanging)
        uit.append(_strip_sql_commentaar(tekst))
    return uit


def _enable_patroon(tabel: str) -> re.Pattern[str]:
    return re.compile(
        r'ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?(?:"?public"?\.)?"?'
        + re.escape(tabel)
        + r'"?\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY',
        re.I,
    )


def _policy_patroon(tabel: str) -> re.Pattern[str]:
    return re.compile(
        r'CREATE\s+POLICY\s+\S+\s+ON\s+(?:ONLY\s+)?(?:"?public"?\.)?"?'
        + re.escape(tabel)
        + r'"?(?![\w"])',
        re.I,
    )


def dekking_van(tabel: str, repo_root: Path) -> Dekking:
    """Welke ACTIEVE migraties zetten RLS aan op `tabel` en maken er een policy op?"""
    dekking = Dekking()
    enable, policy = _enable_patroon(tabel), _policy_patroon(tabel)
    for bestand in sorted((repo_root / _ACTIEVE_MAP).glob("*.py")):
        tree = ast.parse(bestand.read_text(encoding="utf-8"))
        aanroepen = _Aanroepen()
        aanroepen.visit(tree)
        zoeker = _Zoeker(_module_constanten(tree), aanroepen)
        zoeker.visit(tree)
        teksten = [t for s, v in zoeker.sjablonen for t in _uitwerkingen(s, v)]
        if any(enable.search(t) for t in teksten):
            dekking.enable.append(bestand.name)
        if any(policy.search(t) for t in teksten):
            dekking.policy.append(bestand.name)
    return dekking


# --- de echte boom -----------------------------------------------------------------------


def test_user_roles_has_row_level_security_enabled_in_an_active_migration() -> None:
    """Element 1: `ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY` staat in `upgrade()`."""
    dekking = dekking_van(_TABEL, _REPO_ROOT)

    assert dekking.enable, (
        f"Geen enkele migratie in {_ACTIEVE_MAP.as_posix()} zet ROW LEVEL SECURITY aan op "
        f"`{_TABEL}`. Een policy op een tabel met RLS UIT wordt nooit geevalueerd, en "
        "`user_roles` heeft zonder dit geen enkele databasebescherming (OP-190)."
    )


def test_user_roles_has_a_policy_in_an_active_migration() -> None:
    """Element 2: `CREATE POLICY <naam> ON user_roles` staat in een migratie."""
    dekking = dekking_van(_TABEL, _REPO_ROOT)

    assert dekking.policy, (
        f"Geen enkele migratie in {_ACTIEVE_MAP.as_posix()} maakt een policy op `{_TABEL}`. "
        "De docstring van 20260915_rls_resterende_tabellen.py noemt de tabel, maar een "
        "docstring is geen policy (OP-190)."
    )


def test_the_analysis_finds_roles_in_the_real_chain() -> None:
    """Niet leeg: dezelfde analyse vindt `roles` in de echte keten, via het lus-idioom."""
    dekking = dekking_van("roles", _REPO_ROOT)

    assert "20260915_rls_resterende_tabellen.py" in dekking.enable, (
        f"De analyse vindt ENABLE op `roles` niet in 20260915_rls_resterende_tabellen.py "
        f"(gevonden in: {dekking.enable}). Dan leest de parser de keten niet en zeggen de "
        "twee tests hierboven niets."
    )


def test_the_analysis_finds_the_roles_policy_in_the_real_chain() -> None:
    dekking = dekking_van("roles", _REPO_ROOT)

    assert "20260915_rls_resterende_tabellen.py" in dekking.policy, (
        f"De analyse vindt de policy op `roles` niet (gevonden in: {dekking.policy}). "
        "Dan leest de parser het CREATE POLICY-idioom niet."
    )


def test_only_the_active_chain_is_read() -> None:
    """De legacy-map in de root telt niet; alleen `src/alembic/versions/`."""
    assert _ACTIEVE_MAP == Path("src/alembic/versions"), (
        f"De guard leest {_ACTIEVE_MAP}, niet de actieve keten."
    )


# --- mutanten ----------------------------------------------------------------------------

_BEIDE = """
    op.execute("ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY user_roles_tenant_isolation ON user_roles FOR ALL "
        "USING (true) WITH CHECK (true)"
    )
"""

_KOP = """
import sqlalchemy as sa
from alembic import op

revision = "mutant_0001"
down_revision = None
"""

_LUS = '''
{kop}
_TABELLEN = ({tabellen})

def upgrade() -> None:
    for tabel in _TABELLEN:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{{tabel}}') IS NULL THEN
                        RETURN;
                    END IF;
                    EXECUTE 'ALTER TABLE {{tabel}} ENABLE ROW LEVEL SECURITY';
                    EXECUTE $q$CREATE POLICY rls_{{tabel}} ON {{tabel}} FOR ALL USING (true)$q$;
                END $$;
                """
            )
        )

def downgrade() -> None:
    pass
'''

_HULP = """
{kop}

def _beveilig(tabel: str) -> None:
    op.execute(f"ALTER TABLE {{tabel}} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY p ON {{tabel}} FOR ALL USING (true)")

def upgrade() -> None:
    _beveilig("{tabel}")

def downgrade() -> None:
    pass
"""


def _functies(upgrade_body: str, downgrade_body: str = "    pass", upgrade_doc: str = "") -> str:
    doc = f'    """{upgrade_doc}"""\n' if upgrade_doc else ""
    return (
        f"{_KOP}\n\ndef upgrade() -> None:\n{doc}{textwrap.indent(textwrap.dedent(upgrade_body), '    ').rstrip()}\n"
        f"\n\ndef downgrade() -> None:\n{textwrap.indent(textwrap.dedent(downgrade_body), '    ').rstrip()}\n"
    ).replace("    \n", "\n")


# naam -> (bronbestand, ENABLE verwacht gevonden, POLICY verwacht gevonden)
MUTANTEN: dict[str, tuple[str, bool, bool]] = {
    "beide-direct-in-upgrade": (_functies(_BEIDE), True, True),
    "beide-via-sa-text-en-plus": (
        _functies(
            """
            op.execute(sa.text("ALTER TABLE " + "user_roles ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.text("CREATE POLICY p ON " + "user_roles FOR ALL USING (true)"))
            """
        ),
        True,
        True,
    ),
    "lus-met-user-roles-in-de-tuple": (
        _LUS.format(kop=_KOP, tabellen='"roles", "user_roles"'),
        True,
        True,
    ),
    "lus-zonder-user-roles-in-de-tuple": (
        _LUS.format(kop=_KOP, tabellen='"roles", "skills"'),
        False,
        False,
    ),
    "hulpfunctie-met-user-roles": (_HULP.format(kop=_KOP, tabel="user_roles"), True, True),
    "hulpfunctie-met-andere-tabel": (_HULP.format(kop=_KOP, tabel="roles"), False, False),
    "alleen-in-de-moduledocstring": (
        '"""ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY; '
        'CREATE POLICY p ON user_roles FOR ALL USING (true)."""\n'
        + _functies("op.execute('SELECT 1')"),
        False,
        False,
    ),
    "alleen-in-de-docstring-van-upgrade": (
        _functies(
            "op.execute('SELECT 1')",
            upgrade_doc=(
                "ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY; "
                "CREATE POLICY p ON user_roles FOR ALL USING (true)"
            ),
        ),
        False,
        False,
    ),
    "alleen-in-een-python-commentaar": (
        _functies(
            """
            # op.execute("ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY")
            # op.execute("CREATE POLICY p ON user_roles FOR ALL USING (true)")
            op.execute("SELECT 1")
            """
        ),
        False,
        False,
    ),
    "alleen-in-sql-commentaar": (
        _functies(
            '''
            op.execute(
                """
                -- ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;
                /* CREATE POLICY p ON user_roles FOR ALL USING (true) */
                SELECT 1
                """
            )
            '''
        ),
        False,
        False,
    ),
    "alleen-in-downgrade": (
        _functies("op.execute('SELECT 1')", downgrade_body=_BEIDE),
        False,
        False,
    ),
    "andere-tabel-user-roles-audit": (
        _functies(
            """
            op.execute("ALTER TABLE user_roles_audit ENABLE ROW LEVEL SECURITY")
            op.execute("CREATE POLICY p ON user_roles_audit FOR ALL USING (true)")
            """
        ),
        False,
        False,
    ),
    "andere-tabel-roles": (
        _functies(
            """
            op.execute("ALTER TABLE roles ENABLE ROW LEVEL SECURITY")
            op.execute("CREATE POLICY p ON roles FOR ALL USING (true)")
            """
        ),
        False,
        False,
    ),
    "alleen-enable-geen-policy": (
        _functies('op.execute("ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY")'),
        True,
        False,
    ),
    "alleen-policy-geen-enable": (
        _functies('op.execute("CREATE POLICY p ON user_roles FOR ALL USING (true)")'),
        False,
        True,
    ),
    "disable-in-plaats-van-enable": (
        _functies(
            """
            op.execute("ALTER TABLE user_roles DISABLE ROW LEVEL SECURITY")
            op.execute("CREATE POLICY p ON user_roles FOR ALL USING (true)")
            """
        ),
        False,
        True,
    ),
}


def _plaats(repo_root: Path, bron: str, onder: Path = _ACTIEVE_MAP) -> None:
    map_ = repo_root / onder
    map_.mkdir(parents=True, exist_ok=True)
    (map_ / "mutant.py").write_text(bron, encoding="utf-8")


@pytest.mark.parametrize("naam", sorted(MUTANTEN))
def test_enable_is_detected_exactly_when_it_is_really_there(naam: str, tmp_path: Path) -> None:
    bron, verwacht_enable, _ = MUTANTEN[naam]
    _plaats(tmp_path, bron)

    gevonden = bool(dekking_van(_TABEL, tmp_path).enable)

    assert gevonden is verwacht_enable, (
        f"Mutant `{naam}`: ENABLE gevonden={gevonden}, verwacht={verwacht_enable}. "
        "De guard ziet iets wat er niet staat, of mist iets wat er wel staat."
    )


@pytest.mark.parametrize("naam", sorted(MUTANTEN))
def test_policy_is_detected_exactly_when_it_is_really_there(naam: str, tmp_path: Path) -> None:
    bron, _, verwacht_policy = MUTANTEN[naam]
    _plaats(tmp_path, bron)

    gevonden = bool(dekking_van(_TABEL, tmp_path).policy)

    assert gevonden is verwacht_policy, (
        f"Mutant `{naam}`: policy gevonden={gevonden}, verwacht={verwacht_policy}. "
        "De guard ziet iets wat er niet staat, of mist iets wat er wel staat."
    )


def test_a_migration_in_the_legacy_folder_does_not_count_for_enable(tmp_path: Path) -> None:
    _plaats(tmp_path, _functies(_BEIDE), onder=Path("alembic") / "versions")

    assert not dekking_van(_TABEL, tmp_path).enable, (
        "Een migratie in de legacy-map `alembic/versions/` telt mee. Die map draait niet "
        "mee in `alembic -c src/alembic.ini upgrade head`."
    )


def test_a_migration_in_the_legacy_folder_does_not_count_for_the_policy(tmp_path: Path) -> None:
    _plaats(tmp_path, _functies(_BEIDE), onder=Path("alembic") / "versions")

    assert not dekking_van(_TABEL, tmp_path).policy, (
        "Een migratie in de legacy-map `alembic/versions/` telt mee. Die map draait niet "
        "mee in `alembic -c src/alembic.ini upgrade head`."
    )


def test_a_correct_migration_added_to_a_copy_of_the_real_chain_is_accepted_for_enable(
    tmp_path: Path,
) -> None:
    """De legitiem-lijkende kant in de echte context: zonder deze helft is "weiger altijd" geldig."""
    shutil.copytree(_REPO_ROOT / _ACTIEVE_MAP, tmp_path / _ACTIEVE_MAP)
    (tmp_path / _ACTIEVE_MAP / "99999999_nieuw.py").write_text(_functies(_BEIDE), encoding="utf-8")

    assert "99999999_nieuw.py" in dekking_van(_TABEL, tmp_path).enable, (
        "Een correcte migratie naast de echte keten wordt niet herkend voor ENABLE."
    )


def test_a_correct_migration_added_to_a_copy_of_the_real_chain_is_accepted_for_the_policy(
    tmp_path: Path,
) -> None:
    shutil.copytree(_REPO_ROOT / _ACTIEVE_MAP, tmp_path / _ACTIEVE_MAP)
    (tmp_path / _ACTIEVE_MAP / "99999999_nieuw.py").write_text(_functies(_BEIDE), encoding="utf-8")

    assert "99999999_nieuw.py" in dekking_van(_TABEL, tmp_path).policy, (
        "Een correcte migratie naast de echte keten wordt niet herkend voor de policy."
    )
