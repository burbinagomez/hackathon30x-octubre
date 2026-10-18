"""El login es de Supabase Auth (decisión del dueño, 2026-10-18): no quedan rastros del login propio."""
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MIGRACIONES = BACKEND.parent / "supabase" / "migrations"
OBSOLETO = ("hmac_email", "EMAIL_HMAC_CLAVE", "SESSION_SECRET", "usuario_para_login", "email_hmac", "hash_clave", "scrypt")


def test_no_quedan_rastros_del_login_propio():
    archivos = [*(BACKEND / "app").rglob("*.py"), *(BACKEND / "scripts").glob("*"), *MIGRACIONES.glob("*.sql")]
    assert archivos  # una lista vacía dejaría el test verde sin probar nada
    hallazgos = sorted(f"{a.relative_to(BACKEND.parent)}: {palabra}"
                       for a in archivos if a.is_file()
                       for palabra in OBSOLETO if palabra in a.read_text())
    assert hallazgos == []
