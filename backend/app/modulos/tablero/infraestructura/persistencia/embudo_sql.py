"""SQL del embudo del tablero: el unico lugar del tablero con permiso para leer la tabla de leads.

Solo cuenta personas juridicas: una natural nunca se contacta, asi que no entra al embudo.
Solo devuelve conteos de leads distintos por fuente (y en total); nunca una columna de contacto. Un lead de dos fuentes
suma en las dos y el total no lo duplica. La RLS de leads, lead_fuentes y calificaciones filtra el tenant.
Las consultas devuelven exactamente las columnas que lista test_tablero_embudo.py.
"""
from sqlalchemy import text

_CONTEOS = """count(DISTINCT lf.lead_id) FILTER (WHERE l.tipo_titular = 'juridica' AND l.enriquecido_en IS NOT NULL) AS enriquecidos,
       count(DISTINCT lf.lead_id) FILTER (WHERE l.tipo_titular = 'juridica' AND l.contactable) AS contactables,
       count(DISTINCT lf.lead_id) FILTER (WHERE l.tipo_titular = 'juridica' AND l.telefono_cifrado IS NOT NULL) AS con_telefono,
       count(DISTINCT lf.lead_id) FILTER (WHERE q.calificado) AS calificados"""
_DESDE = """FROM lead_fuentes lf
JOIN leads l ON l.tenant_id = lf.tenant_id AND l.id = lf.lead_id
LEFT JOIN calificaciones q ON q.tenant_id = lf.tenant_id AND q.lead_id = lf.lead_id"""

SQL_EMBUDO_FUENTES = text(f"SELECT lf.fuente, {_CONTEOS}\n{_DESDE}\nGROUP BY lf.fuente")
SQL_EMBUDO_TOTAL = text(f"SELECT {_CONTEOS}\n{_DESDE}")
