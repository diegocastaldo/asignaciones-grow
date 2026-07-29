"""
Generador de archivos de carga masiva — IAS y S/4HANA Cloud (Grow)
Versión 1: herramientas aisladas.
"""

import pandas as pd
import streamlit as st

import core

st.set_page_config(
    page_title="Cargas masivas Grow",
    page_icon="📤",
    layout="wide",
)

st.title("Generador de archivos de carga masiva")
st.caption(
    "Genera los archivos que reciben **IAS** (import de usuarios) y "
    "**Maintain Business Users** (asignación de roles) en S/4HANA Cloud Public Edition."
)

tab_ias, tab_roles = st.tabs(["👤 Usuarios → IAS", "🔑 Roles → Maintain Business Users"])

# ===========================================================================
# TAB 1 — IAS
# ===========================================================================
with tab_ias:
    st.subheader("Import de usuarios en Identity Authentication (IAS)")
    st.markdown(
        "Subí un listado con **nombre, apellido y mail**. La herramienta genera el CSV "
        "con atributos SCIM (`status,loginName,mail,firstName,lastName,displayName`) "
        "listo para *Users & Authorizations → Import Users*."
    )

    archivo = st.file_uploader(
        "Listado de usuarios (.xlsx o .csv)",
        type=["xlsx", "xlsm", "xls", "csv"],
        key="up_ias",
    )

    if archivo:
        try:
            df = core.leer_archivo(archivo, archivo.name)
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
            st.stop()

        st.dataframe(df.head(10))
        cols = list(df.columns)

        c1, c2, c3 = st.columns(3)
        col_nombre = c1.selectbox(
            "Columna de Nombre", cols,
            index=core.adivinar_columna(cols, ["nombre", "first"]),
        )
        col_apellido = c2.selectbox(
            "Columna de Apellido", cols,
            index=core.adivinar_columna(cols, ["apellido", "last"]),
        )
        col_mail = c3.selectbox(
            "Columna de Mail", cols,
            index=core.adivinar_columna(cols, ["mail", "correo", "email"]),
        )

        c4, c5, c6 = st.columns(3)
        regla = c4.selectbox(
            "Regla para loginName",
            options=["mail", "mail_local", "nombre.apellido", "inicial_apellido"],
            format_func={
                "mail": "Mail completo (recomendado)",
                "mail_local": "Parte local del mail (antes de @)",
                "nombre.apellido": "nombre.apellido (normalizado)",
                "inicial_apellido": "Inicial + apellido (jperez)",
            }.get,
        )
        status = c5.selectbox("Status inicial", ["active", "inactive", "new"])
        incluir_dn = c6.checkbox("Incluir displayName", value=True)

        if st.button("Generar CSV para IAS", type="primary"):
            res = core.construir_ias(
                df, col_nombre, col_apellido, col_mail,
                regla_login=regla, status=status, incluir_display_name=incluir_dn,
            )
            for a in res.advertencias:
                st.warning(a)
            if res.errores:
                st.error(
                    f"**{len(res.errores)} error(es). No se genera el archivo hasta corregirlos:**\n\n- "
                    + "\n- ".join(res.errores)
                )
            if res.ok:
                st.success(f"Listo: {len(res.df)} usuarios.")
                st.dataframe(res.df)
                st.download_button(
                    "⬇️ Descargar import_usuarios_IAS.csv",
                    data=core.csv_ias(res.df),
                    file_name="import_usuarios_IAS.csv",
                    mime="text/csv",
                )
                st.info(
                    "En IAS el import matchea usuarios existentes por identificador. "
                    "Después del import, disparás los mails de activación desde la consola si corresponde."
                )

# ===========================================================================
# TAB 2 — Maintain Business Users
# ===========================================================================
with tab_roles:
    st.subheader("Asignación masiva de Business Roles (Maintain Business Users)")
    st.markdown(
        "Subí un listado con **mail y roles** (los roles pueden ir varios en una celda, "
        "separados por `;` `,` o salto de línea, o una fila por rol). "
        "Para resolver el **User Name** —obligatorio en el upload— cargá también el "
        "**export del tenant** (botón *Download* en Maintain Business Users)."
    )
    st.warning(
        "⚠️ **KBA 3738656:** si el archivo de upload tiene filas sin *User Name*, el sistema "
        "asigna esos roles a **todos** los usuarios del tenant que no tienen user name. "
        "Esta herramienta bloquea la generación si algún User Name queda vacío."
    )

    archivo_in = st.file_uploader(
        "1) Listado de asignaciones: mail + roles (.xlsx o .csv)",
        type=["xlsx", "xlsm", "xls", "csv"],
        key="up_asig",
    )
    archivo_exp = st.file_uploader(
        "2) Export del tenant — Maintain Business Users → Download (.xlsx o .csv) — recomendado",
        type=["xlsx", "xlsm", "xls", "csv"],
        key="up_export",
    )

    if archivo_in:
        try:
            df_in = core.leer_archivo(archivo_in, archivo_in.name)
        except Exception as e:
            st.error(f"No se pudo leer el listado: {e}")
            st.stop()

        st.dataframe(df_in.head(10))
        cols_in = list(df_in.columns)

        c1, c2 = st.columns(2)
        col_mail_in = c1.selectbox(
            "Columna de Mail", cols_in,
            index=core.adivinar_columna(cols_in, ["mail", "correo", "email"]),
        )
        col_roles_in = c2.selectbox(
            "Columna de Roles", cols_in,
            index=core.adivinar_columna(cols_in, ["rol", "role"]),
        )

        df_exp = None
        col_mail_exp = col_user_exp = col_uid_exp = col_user_in = None

        if archivo_exp:
            try:
                df_exp = core.leer_archivo(archivo_exp, archivo_exp.name)
            except Exception as e:
                st.error(f"No se pudo leer el export del tenant: {e}")
                st.stop()
            cols_exp = list(df_exp.columns)
            st.markdown("**Mapeo de columnas del export del tenant:**")
            c3, c4, c5 = st.columns(3)
            col_mail_exp = c3.selectbox(
                "Email (export)", cols_exp,
                index=core.adivinar_columna(cols_exp, ["mail", "correo", "email"]),
            )
            col_user_exp = c4.selectbox(
                "User Name (export)", cols_exp,
                index=core.adivinar_columna(cols_exp, ["user name", "username", "usuario"]),
            )
            col_uid_exp = c5.selectbox(
                "User ID (export, opcional)", ["(ninguna)"] + cols_exp,
                index=1 + core.adivinar_columna(cols_exp, ["user id", "userid"])
                if core.adivinar_columna(cols_exp, ["user id", "userid"]) else 0,
            )
            if col_uid_exp == "(ninguna)":
                col_uid_exp = None
        else:
            st.info(
                "Sin el export del tenant, el listado debe traer una columna con el **User Name** de cada usuario."
            )
            col_user_in = st.selectbox(
                "Columna de User Name en el listado", ["(ninguna)"] + cols_in,
            )
            if col_user_in == "(ninguna)":
                col_user_in = None

        with st.expander("Opcional: validar Role IDs contra un catálogo"):
            archivo_roles = st.file_uploader(
                "Export de Maintain Business Roles (.xlsx o .csv)",
                type=["xlsx", "xlsm", "xls", "csv"],
                key="up_cat",
            )
            roles_validos = None
            if archivo_roles:
                df_cat = core.leer_archivo(archivo_roles, archivo_roles.name)
                cols_cat = list(df_cat.columns)
                col_rol_cat = st.selectbox(
                    "Columna con el Business Role ID", cols_cat,
                    index=core.adivinar_columna(cols_cat, ["role id", "business role", "rol"]),
                )
                roles_validos = {core.limpiar(r) for r in df_cat[col_rol_cat] if core.limpiar(r)}
                st.caption(f"Catálogo cargado: {len(roles_validos)} roles.")

        if st.button("Generar CSV de asignaciones", type="primary"):
            res = core.construir_asignaciones(
                df_in, col_mail_in, col_roles_in,
                df_export=df_exp,
                col_mail_export=col_mail_exp,
                col_username_export=col_user_exp,
                col_userid_export=col_uid_exp,
                col_username_input=col_user_in,
                roles_validos=roles_validos,
            )
            for a in res.advertencias:
                st.warning(a)
            if res.errores:
                st.error(
                    f"**{len(res.errores)} error(es). No se genera el archivo hasta corregirlos:**\n\n- "
                    + "\n- ".join(res.errores)
                )
            if res.ok:
                usuarios = res.df["User Name"].nunique()
                st.success(f"Listo: {len(res.df)} asignaciones para {usuarios} usuarios.")
                st.dataframe(res.df)
                st.download_button(
                    "⬇️ Descargar asignacion_roles_MBU.csv",
                    data=core.csv_mbu(res.df),
                    file_name="asignacion_roles_MBU.csv",
                    mime="text/csv",
                )
                st.info(
                    "Antes del primer upload en un tenant nuevo, comparalo con el template que baja el app "
                    "(Maintain Business Users → Upload → Download Template) por si el header cambió con el release."
                )
