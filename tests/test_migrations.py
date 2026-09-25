"""The upstream migration runner (scripts/resource/init_db.py) splits files on ';'
before stripping comments, so a ';' anywhere except at a statement end breaks it."""

from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "resource" / "sql"


def test_layertoll_migration_has_no_inline_semicolons():
    for line_no, line in enumerate((SQL_DIR / "version-1.4.0.sql").read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.rstrip()
        assert ";" not in stripped[:-1], f"line {line_no}: ';' only allowed as statement terminator"


def test_migration_statements_split_like_the_runner():
    content = (SQL_DIR / "version-1.4.0.sql").read_text(encoding="utf-8")
    statements = [s for s in content.split(";") if s.strip() and not all(l.strip().startswith("--") or not l.strip() for l in s.splitlines())]
    heads = [" ".join(l for l in s.strip().splitlines() if not l.strip().startswith("--")).split()[0].upper() for s in statements]
    assert set(heads) <= {"SET", "ALTER", "CREATE", "UPDATE", "INSERT"}
    assert heads.count("ALTER") == 3 and heads.count("CREATE") == 2
