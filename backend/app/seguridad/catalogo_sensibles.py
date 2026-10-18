"""Columnas con datos personales (principio VI). Las usan los tests de cifrado; el 006 y el 007 suman las suyas.

Nombre y dirección de los titulares no jurídicos; teléfono y email de contacto, siempre (006).
"""

# (tabla, columna): siempre bytea cifrado con AES-GCM (AAD: columna + tenant + lead).
CIFRADAS = {("leads", "nombre_cifrado"), ("leads", "direccion_cifrada"), ("leads", "telefono_cifrado"),
            ("leads", "email_cifrado")}

# (tabla, columna): en claro solo si tipo_titular = 'juridica'; en cualquier otro titular van NULL.
CONDICIONALES = {("leads", "nombre"), ("leads", "direccion")}
