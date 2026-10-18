from uuid import UUID

from sqlalchemy import Engine, text

from app.modulos.acceso.dominio.modelos import AccesoUsuario


def tenant_de_usuario(engine: Engine, auth_user_id: UUID) -> AccesoUsuario | None:
    """La fila de ESE usuario, o None. `usuarios` no es legible por app_rt: solo entra esta función SECURITY DEFINER.

    Sin `app.tenant_id`: se corre antes de conocer el tenant.
    """
    with engine.connect() as conexion:
        fila = conexion.execute(
            text("SELECT tenant_id, idioma_usuario, idioma_tenant FROM tenant_de_usuario(:uid)"),
            {"uid": auth_user_id},
        ).first()
    return None if fila is None else AccesoUsuario(fila.tenant_id, fila.idioma_usuario, fila.idioma_tenant)
