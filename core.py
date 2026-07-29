"""
core.py — Lógica de transformación y validación para asignaciones masivas
en SAP S/4HANA Cloud Public Edition (Grow) e Identity Authentication (IAS).

Separado de la UI (Streamlit) para poder reutilizarlo en la versión 2
(integración con la planilla de relevamiento de roles).

Formatos destino:
  1) IAS — Import Users CSV (atributos SCIM):
     Obligatorios: status, mail, lastName + (loginName o userName).
     Sin espacios alrededor de las comas. UTF-8.
  2) Maintain Business Users — Upload User Role Assignments (CSV UTF-8):
     Patrón: User Name (obligatorio), User ID, Email, Global User ID,
     Role ID (obligatorio).
     ¡OJO! KBA 3738656: si una fila queda sin User Name, el sistema asigna
     los roles a TODOS los usuarios del tenant que no tienen user name.
     Por eso la validación de User Name vacío es BLOQUEANTE.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

_RE_MAIL = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def limpiar(valor) -> str:
    """Convierte a string, quita espacios en extremos y colapsa internos."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    s = str(valor).strip()
    # NBSP y similares que suelen venir de Excel
    s = s.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", s)


def quitar_acentos(texto: str) -> str:
    """Elimina tildes/diacríticos (á→a, ñ→n, ü→u)."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_login(texto: str) -> str:
    """Normaliza un fragmento para loginName: sin tildes, minúsculas,
    espacios → nada, solo [a-z0-9._-]."""
    s = quitar_acentos(limpiar(texto)).lower()
    s = s.replace(" ", "")
    return re.sub(r"[^a-z0-9._\-]", "", s)


def mail_valido(mail: str) -> bool:
    return bool(_RE_MAIL.match(limpiar(mail)))


def generar_login(nombre: str, apellido: str, mail: str, regla: str) -> str:
    """Genera loginName según la regla configurada.

    Reglas:
      - "mail": el mail completo tal cual (en minúsculas)
      - "mail_local": la parte local del mail (antes de @)
      - "nombre.apellido": primer nombre + '.' + primer apellido, normalizado
      - "inicial_apellido": inicial del nombre + primer apellido, normalizado
    """
    mail = limpiar(mail).lower()
    if regla == "mail":
        return mail
    if regla == "mail_local":
        return mail.split("@", 1)[0] if "@" in mail else mail
    primer_nombre = normalizar_login(limpiar(nombre).split(" ")[0]) if limpiar(nombre) else ""
    primer_apellido = normalizar_login(limpiar(apellido).split(" ")[0]) if limpiar(apellido) else ""
    if regla == "nombre.apellido":
        return f"{primer_nombre}.{primer_apellido}".strip(".")
    if regla == "inicial_apellido":
        return f"{primer_nombre[:1]}{primer_apellido}"
    raise ValueError(f"Regla de loginName desconocida: {regla}")


def separar_roles(celda) -> list[str]:
    """Divide una celda que puede contener varios roles separados por
    ';', ',', salto de línea o '|'. Devuelve lista sin vacíos ni duplicados
    (conserva el orden)."""
    s = limpiar(celda)
    if not s:
        return []
    partes = re.split(r"[;,|\n]+", s)
    vistos: list[str] = []
    for p in partes:
        p = p.strip()
        if p and p not in vistos:
            vistos.append(p)
    return vistos


# ---------------------------------------------------------------------------
# Resultado con errores/advertencias
# ---------------------------------------------------------------------------

@dataclass
class Resultado:
    df: pd.DataFrame | None = None
    errores: list[str] = field(default_factory=list)      # bloqueantes
    advertencias: list[str] = field(default_factory=list)  # no bloqueantes

    @property
    def ok(self) -> bool:
        return not self.errores and self.df is not None and len(self.df) > 0


# ---------------------------------------------------------------------------
# Herramienta 1: IAS Import Users CSV
# ---------------------------------------------------------------------------

def construir_ias(
    df: pd.DataFrame,
    col_nombre: str,
    col_apellido: str,
    col_mail: str,
    regla_login: str = "mail",
    status: str = "active",
    incluir_display_name: bool = True,
) -> Resultado:
    """Transforma un listado (nombre, apellido, mail) al CSV de import de IAS."""
    res = Resultado()
    filas = []

    for idx, fila in df.iterrows():
        n_fila = idx + 2  # 1-indexed + header, para que coincida con Excel
        nombre = limpiar(fila.get(col_nombre))
        apellido = limpiar(fila.get(col_apellido))
        mail = limpiar(fila.get(col_mail)).lower()

        # Fila totalmente vacía: se ignora en silencio
        if not nombre and not apellido and not mail:
            continue

        if not mail:
            res.errores.append(f"Fila {n_fila}: mail vacío (mail es obligatorio en IAS).")
            continue
        if not mail_valido(mail):
            res.errores.append(f"Fila {n_fila}: mail con formato inválido: '{mail}'.")
            continue
        if not apellido:
            res.errores.append(f"Fila {n_fila}: apellido vacío (lastName es obligatorio en IAS).")
            continue
        if not nombre:
            res.advertencias.append(f"Fila {n_fila}: nombre vacío (firstName quedará en blanco).")

        login = generar_login(nombre, apellido, mail, regla_login)
        if not login:
            res.errores.append(f"Fila {n_fila}: no se pudo generar loginName con la regla '{regla_login}'.")
            continue

        registro = {
            "status": status,
            "loginName": login,
            "mail": mail,
            "firstName": nombre,
            "lastName": apellido,
        }
        if incluir_display_name:
            registro["displayName"] = f"{nombre} {apellido}".strip()
        filas.append(registro)

    if not filas and not res.errores:
        res.errores.append("El archivo no contiene filas con datos.")
        return res

    out = pd.DataFrame(filas)

    # Duplicados
    if len(out):
        dup_mail = out[out.duplicated("mail", keep=False)]["mail"].unique().tolist()
        for m in dup_mail:
            res.errores.append(f"Mail duplicado en el listado: '{m}'. IAS matchea por mail; corregí el origen.")
        dup_login = out[out.duplicated("loginName", keep=False)]["loginName"].unique().tolist()
        for l in dup_login:
            if regla_login in ("nombre.apellido", "inicial_apellido", "mail_local"):
                res.errores.append(
                    f"loginName duplicado generado por la regla '{regla_login}': '{l}'. "
                    "Resolvé manualmente (homónimos) o usá la regla 'mail'."
                )

    res.df = out
    return res


def csv_ias(df: pd.DataFrame) -> bytes:
    """Serializa el DataFrame al CSV que espera IAS: coma como separador,
    sin espacios, UTF-8 sin BOM, salto de línea \\n."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Herramienta 2: Maintain Business Users — Upload User Role Assignments
# ---------------------------------------------------------------------------

HEADER_MBU = ["User Name", "User ID", "Email", "Global User ID", "Role ID"]


def construir_asignaciones(
    df_input: pd.DataFrame,
    col_mail_input: str,
    col_roles_input: str,
    df_export: pd.DataFrame | None = None,
    col_mail_export: str | None = None,
    col_username_export: str | None = None,
    col_userid_export: str | None = None,
    col_username_input: str | None = None,
    roles_validos: set[str] | None = None,
) -> Resultado:
    """Construye el CSV de asignación de roles para Maintain Business Users.

    El User Name se resuelve así:
      - Si hay export del tenant (df_export): mail → User Name (recomendado).
      - Si no, se exige una columna User Name en el propio input
        (col_username_input).

    Validación BLOQUEANTE: ninguna fila puede quedar con User Name vacío
    (KBA 3738656: asignaría los roles a todos los usuarios sin user name).
    """
    res = Resultado()

    # --- Tabla de mapeo mail -> (User Name, User ID) -----------------------
    mapeo: dict[str, tuple[str, str]] = {}
    if df_export is not None:
        if not col_mail_export or not col_username_export:
            res.errores.append("Falta indicar las columnas de Email y User Name en el export del tenant.")
            return res
        for _, fila in df_export.iterrows():
            m = limpiar(fila.get(col_mail_export)).lower()
            u = limpiar(fila.get(col_username_export))
            uid = limpiar(fila.get(col_userid_export)) if col_userid_export else ""
            if not m:
                continue
            if m in mapeo and mapeo[m][0] != u:
                res.advertencias.append(
                    f"El export del tenant tiene el mail '{m}' repetido con distinto User Name "
                    f"('{mapeo[m][0]}' vs '{u}'). Se usa el primero."
                )
                continue
            mapeo[m] = (u, uid)
        usuarios_sin_username = [m for m, (u, _) in mapeo.items() if not u]
        for m in usuarios_sin_username:
            res.advertencias.append(
                f"En el export del tenant, el usuario con mail '{m}' NO tiene User Name mantenido. "
                "Si necesitás asignarle roles, primero mantené su User Name en Maintain Business Users."
            )

    # --- Procesar input ----------------------------------------------------
    filas = []
    for idx, fila in df_input.iterrows():
        n_fila = idx + 2
        mail = limpiar(fila.get(col_mail_input)).lower()
        roles = separar_roles(fila.get(col_roles_input))

        if not mail and not roles:
            continue
        if not mail:
            res.errores.append(f"Fila {n_fila}: mail vacío.")
            continue
        if not mail_valido(mail):
            res.errores.append(f"Fila {n_fila}: mail con formato inválido: '{mail}'.")
            continue
        if not roles:
            res.advertencias.append(f"Fila {n_fila}: '{mail}' no tiene roles informados; se omite.")
            continue

        # Resolver User Name
        user_name, user_id = "", ""
        if df_export is not None:
            if mail not in mapeo:
                res.errores.append(
                    f"Fila {n_fila}: el mail '{mail}' no existe en el export del tenant. "
                    "Verificá que el usuario esté creado antes de asignarle roles."
                )
                continue
            user_name, user_id = mapeo[mail]
        elif col_username_input:
            user_name = limpiar(fila.get(col_username_input))

        if not user_name:
            res.errores.append(
                f"Fila {n_fila}: '{mail}' quedaría SIN User Name. Bloqueado: subir así el archivo "
                "asignaría los roles a todos los usuarios del tenant sin user name (KBA 3738656)."
            )
            continue

        for rol in roles:
            if roles_validos is not None and rol not in roles_validos:
                res.errores.append(
                    f"Fila {n_fila}: el rol '{rol}' no existe en el catálogo de Business Roles cargado."
                )
                continue
            filas.append({
                "User Name": user_name,
                "User ID": user_id,
                "Email": mail,
                "Global User ID": "",
                "Role ID": rol,
            })

    if not filas and not res.errores:
        res.errores.append("No se generó ninguna asignación. Revisá el archivo de entrada.")
        return res

    out = pd.DataFrame(filas, columns=HEADER_MBU)

    # Deduplicar pares usuario-rol (puede venir el mismo par en dos filas)
    antes = len(out)
    out = out.drop_duplicates(subset=["User Name", "Role ID"]).reset_index(drop=True)
    if len(out) < antes:
        res.advertencias.append(f"Se eliminaron {antes - len(out)} asignaciones duplicadas (mismo usuario y rol).")

    res.df = out
    return res


def csv_mbu(df: pd.DataFrame, header: list[str] | None = None) -> bytes:
    """CSV UTF-8 para Maintain Business Users. El header es editable por si
    el template del tenant difiere (verificar contra el Download del app)."""
    out = df.copy()
    if header:
        if len(header) != len(out.columns):
            raise ValueError("El header personalizado no coincide en cantidad de columnas.")
        out.columns = header
    buf = io.StringIO()
    out.to_csv(buf, index=False, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Lectura de archivos subidos
# ---------------------------------------------------------------------------

def leer_archivo(archivo, nombre: str) -> pd.DataFrame:
    """Lee un upload de Streamlit (xlsx/xls/csv) a DataFrame, todo como texto."""
    nombre = nombre.lower()
    if nombre.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(archivo, dtype=str).fillna("")
    # CSV: detectar separador automáticamente (coma o punto y coma)
    contenido = archivo.read()
    if isinstance(contenido, bytes):
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
    else:
        texto = contenido
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
        sep = dialecto.delimiter
    except csv.Error:
        sep = ","
    return pd.read_csv(io.StringIO(texto), sep=sep, dtype=str).fillna("")


def adivinar_columna(columnas: list[str], candidatos: list[str]) -> int:
    """Devuelve el índice de la primera columna cuyo nombre matchee alguno de
    los candidatos (búsqueda por substring, sin acentos ni mayúsculas)."""
    normalizadas = [quitar_acentos(c).lower() for c in columnas]
    for cand in candidatos:
        for i, col in enumerate(normalizadas):
            if cand in col:
                return i
    return 0
