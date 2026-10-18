"""El login es de Supabase Auth (decisión del dueño, 2026-10-18): no quedan rastros del login propio."""
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
RAIZ = BACKEND.parent
MIGRACIONES = RAIZ / "supabase" / "migrations"
OBSOLETO = ("hmac_email", "EMAIL_HMAC_CLAVE", "SESSION_SECRET", "usuario_para_login", "email_hmac", "hash_clave", "scrypt")


def test_no_quedan_rastros_del_login_propio():
    # No se mira specs/: ahí las palabras viven a propósito, como historia de lo que se descartó.
    archivos = [*(BACKEND / "app").rglob("*.py"), *(BACKEND / "scripts").glob("*"), *MIGRACIONES.glob("*.sql"),
                RAIZ / ".env.example", BACKEND / "pyproject.toml",
                *(RAIZ / ".github" / "workflows").glob("*"), *(RAIZ / "docs").rglob("*")]
    assert {a.name for a in archivos} >= {".env.example", "pyproject.toml", "ci.yml"}  # los nuevos existen y se leen
    hallazgos = sorted(f"{a.relative_to(RAIZ)}: {palabra}"
                       for a in archivos if a.is_file()
                       for palabra in OBSOLETO if palabra in a.read_text(errors="ignore"))
    assert hallazgos == []
