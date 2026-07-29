# Cargas masivas Grow — IAS y Maintain Business Users

App Streamlit para generar los archivos de carga masiva de usuarios y roles en
SAP S/4HANA Cloud Public Edition (Grow) e Identity Authentication (IAS).

## Herramientas

### 1. Usuarios → IAS
- **Input:** listado con nombre, apellido y mail (.xlsx o .csv).
- **Output:** CSV con atributos SCIM: `status,loginName,mail,firstName,lastName,displayName`.
- Reglas de `loginName` configurables: mail completo, parte local del mail,
  `nombre.apellido` o inicial+apellido (siempre normalizados: sin tildes ni ñ).
- Validaciones bloqueantes: mail vacío o inválido, apellido vacío (`lastName`
  es obligatorio en IAS), mails duplicados, loginName duplicado por homónimos.

### 2. Roles → Maintain Business Users
- **Input A:** listado con mail + roles. Los roles pueden ir varios en una celda
  (separados por `;` `,` `|` o salto de línea) o una fila por rol.
- **Input B (recomendado):** export del tenant (*Maintain Business Users → Download*)
  para resolver el **User Name** a partir del mail.
- **Input C (opcional):** export de *Maintain Business Roles* para validar que
  los Role IDs existan.
- **Output:** CSV UTF-8 con el patrón `User Name, User ID, Email, Global User ID, Role ID`,
  una fila por par usuario-rol, deduplicado.

**Validación crítica (KBA 3738656):** el upload de *Maintain Business Users* asigna
los roles a **todos** los usuarios sin user name si una fila del archivo queda con
*User Name* vacío. La app bloquea la generación en ese caso — nunca genera un
archivo con User Name vacío.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy en Streamlit Cloud

Igual que matriz-seguridad-grow: repo en GitHub con `app.py`, `core.py` y
`requirements.txt`, y crear la app desde share.streamlit.io.

## Estructura

- `core.py` — toda la lógica de transformación y validación (sin dependencia de
  Streamlit). Es lo que se reutiliza en la **versión 2** para leer directamente
  la planilla de relevamiento de roles.
- `app.py` — UI Streamlit (dos tabs).
- `test_core.py` — tests de la lógica (`python3 test_core.py`).

## Versión 2 (pendiente)

Agregar un tercer tab que lea la planilla existente de relevamiento (la que usa
el consultor de seguridad), con mapeo de columnas configurable, y genere ambos
outputs desde esa única fuente.

## Nota sobre releases

El header exacto del template de upload puede variar entre releases del tenant.
Antes del primer uso en un tenant nuevo, comparar contra el template que baja el
propio app (*Upload → Download Template*). La función `core.csv_mbu()` acepta un
header personalizado por ese motivo.
