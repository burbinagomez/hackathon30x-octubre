"""Columnas con datos personales (principio VI). Las usan los tests de cifrado; el 006 y el 007 suman las suyas.

Hoy: nombre y dirección de los titulares no jurídicos. teléfono y email llegan con el bloque de contacto (Pulido P1).
"""

# (tabla, columna): siempre bytea cifrado con AES-GCM (AAD: columna + tenant + lead).
CIFRADAS = {("leads", "nombre_cifrado"), ("leads", "direccion_cifrada")}

# (tabla, columna): en claro solo si tipo_titular = 'juridica'; en cualquier otro titular van NULL.
CONDICIONALES = {("leads", "nombre"), ("leads", "direccion")}
