import pandas as pd
import core

# --- Test 1: IAS ---
df = pd.DataFrame({
    "Nombre": ["María José", "Juán", "", "Pedro", "Ana"],
    "Apellido": ["Núñez", "Pérez", "", "", "López"],
    "Correo electrónico": ["MJ.Nunez@Cliente.com ", "juan.perez@cliente.com", "", "pedro@cliente.com", "ana.lopez@cliente"],
})
res = core.construir_ias(df, "Nombre", "Apellido", "Correo electrónico", regla_login="nombre.apellido")
print("IAS errores:", res.errores)
print("IAS advertencias:", res.advertencias)
if res.df is not None:
    print(res.df)
assert any("apellido vacío" in e for e in res.errores)          # Pedro sin apellido
assert any("formato inválido" in e.lower() for e in res.errores)  # ana.lopez@cliente
assert res.df.iloc[0]["loginName"] == "maria.nunez"
assert res.df.iloc[0]["mail"] == "mj.nunez@cliente.com"

# duplicado por regla
df2 = pd.DataFrame({
    "n": ["Juan", "Juana"], "a": ["Pérez", "Pérez"],
    "m": ["jp1@c.com", "jp2@c.com"],
})
res2 = core.construir_ias(df2, "n", "a", "m", regla_login="inicial_apellido")
assert any("duplicado" in e for e in res2.errores), res2.errores
print("Dup login OK:", res2.errores[0])

print("\nCSV IAS:")
res3 = core.construir_ias(df2, "n", "a", "m", regla_login="mail")
print(core.csv_ias(res3.df).decode())

# --- Test 2: MBU ---
df_in = pd.DataFrame({
    "Email": ["ana@c.com", "beto@c.com", "caro@c.com", "dario@c.com", "ana@c.com"],
    "Roles": ["Z_FI_CONTADOR; Z_MM_COMPRAS", "Z_SD_VENTAS", "", "Z_FI_CONTADOR", "Z_FI_CONTADOR"],
})
df_exp = pd.DataFrame({
    "User Name": ["ANA", "", "CARO"],
    "User ID": ["USR001", "USR002", "USR003"],
    "E-Mail Address": ["ana@c.com", "beto@c.com", "caro@c.com"],
})
res4 = core.construir_asignaciones(
    df_in, "Email", "Roles",
    df_export=df_exp, col_mail_export="E-Mail Address",
    col_username_export="User Name", col_userid_export="User ID",
)
print("\nMBU errores:", res4.errores)
print("MBU advertencias:", res4.advertencias)
# beto sin User Name -> bloqueante; dario no está en export -> bloqueante
assert any("SIN User Name" in e for e in res4.errores)
assert any("no existe en el export" in e for e in res4.errores)
assert not res4.ok  # bloqueado

# caso feliz
df_in_ok = pd.DataFrame({
    "Email": ["ana@c.com", "caro@c.com", "ana@c.com"],
    "Roles": ["Z_FI_CONTADOR; Z_MM_COMPRAS", "Z_SD_VENTAS", "Z_FI_CONTADOR"],
})
res5 = core.construir_asignaciones(
    df_in_ok, "Email", "Roles",
    df_export=df_exp, col_mail_export="E-Mail Address",
    col_username_export="User Name", col_userid_export="User ID",
)
print("\nMBU OK errores:", res5.errores)
print("MBU OK advertencias:", res5.advertencias)
print(res5.df)
assert res5.ok
assert len(res5.df) == 3  # dedup del par ANA + Z_FI_CONTADOR
print("\nCSV MBU:")
print(core.csv_mbu(res5.df).decode())

# validación de catálogo
res6 = core.construir_asignaciones(
    df_in_ok, "Email", "Roles",
    df_export=df_exp, col_mail_export="E-Mail Address",
    col_username_export="User Name",
    roles_validos={"Z_FI_CONTADOR", "Z_SD_VENTAS"},
)
assert any("no existe en el catálogo" in e for e in res6.errores)
print("\nCatálogo OK:", res6.errores)

# input una-fila-por-rol también funciona (celda con un solo rol)
print("\nTodos los tests pasaron ✔")
