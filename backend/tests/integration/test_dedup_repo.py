from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

CORTO = b"\x00" * 28  # nonce de 12 + etiqueta GCM de 16: un bytea de 28 no trae ni un byte de texto
CIFRADO = b"\x00" * 29

CK_NOMBRE = "leads_nombre_segun_titular_ck"
CK_DIRECCION = "leads_direccion_segun_titular_ck"

# (tipo_titular, nombre, nombre_cifrado, direccion, direccion_cifrada) -> CHECK que debe rechazarla, o None si inserta
CASOS = {
    "juridica_en_claro": (("juridica", "Acme SAS", None, "Calle 1", None), None),
    "juridica_sin_direccion": (("juridica", "Acme SAS", None, None, None), None),
    "desconocido_cifrado": (("desconocido", None, CIFRADO, None, None), None),
    "natural_cifrado_con_direccion": (("natural", None, CIFRADO, None, CIFRADO), None),
    "juridica_sin_nombre": (("juridica", None, None, None, None), CK_NOMBRE),
    "juridica_con_nombre_cifrado": (("juridica", "Acme SAS", CIFRADO, None, None), CK_NOMBRE),
    "desconocido_con_nombre_en_claro": (("desconocido", "Tienda", CIFRADO, None, None), CK_NOMBRE),
    "natural_con_nombre_en_claro": (("natural", "Tienda", CIFRADO, None, None), CK_NOMBRE),
    "desconocido_sin_nombre_cifrado": (("desconocido", None, None, None, None), CK_NOMBRE),
    "desconocido_con_nombre_cifrado_de_0_bytes": (("desconocido", None, b"", None, None), CK_NOMBRE),
    "desconocido_con_nombre_cifrado_de_28_bytes": (("desconocido", None, CORTO, None, None), CK_NOMBRE),
    "desconocido_con_direccion_en_claro": (("desconocido", None, CIFRADO, "Calle 1", None), CK_DIRECCION),
    "desconocido_con_direccion_cifrada_de_28_bytes": (("desconocido", None, CIFRADO, None, CORTO), CK_DIRECCION),
    "juridica_con_direccion_cifrada": (("juridica", "Acme SAS", None, None, CIFRADO), CK_DIRECCION),
}


@pytest.mark.parametrize("valores, rechazo", CASOS.values(), ids=CASOS.keys())
def test_check_nombre_segun_tipo_titular(admin, tenants, valores, rechazo):
    tipo, nombre, nombre_cifrado, direccion, direccion_cifrada = valores
    insertar = text(
        "INSERT INTO leads (id, tenant_id, pais, tipo_titular, nombre, nombre_cifrado, direccion, direccion_cifrada) "
        "VALUES (:id, :t, 'CO', :tipo, :nombre, :nombre_cifrado, :direccion, :direccion_cifrada)")
    params = {"id": uuid4(), "t": tenants["a"], "tipo": tipo, "nombre": nombre, "nombre_cifrado": nombre_cifrado,
              "direccion": direccion, "direccion_cifrada": direccion_cifrada}
    if rechazo is None:
        with admin.begin() as c:
            c.execute(insertar, params)
        return
    with pytest.raises(IntegrityError) as exc:
        with admin.begin() as c:
            c.execute(insertar, params)
    assert exc.value.orig.diag.constraint_name == rechazo
