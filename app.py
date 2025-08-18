# app.py — H DECANTS (PDF con leyenda de pago)
# ============================================
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
from datetime import datetime
from dateutil.relativedelta import relativedelta
import base64
from typing import List, Tuple

# =====================
# CONFIG Y CONSTANTES
# =====================
st.set_page_config(page_title="H DECANTS", layout="wide")
LOGO_URL = "https://raw.githubusercontent.com/HarimEG/app-decants/main/hdecants_logo.jpg"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1bjV4EaDNNbJfN4huzbNpTFmj-vfCr7A2474jhO81-bE/edit?gid=1318862509#gid=1318862509"
SHEET_TAB_PRODUCTOS = "Productos"
SHEET_TAB_PEDIDOS   = "Pedidos"
SHEET_TAB_ENVIOS    = "Envios"

ESTATUS_LIST = ["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"]

# =====================
# CABECERA
# =====================
st.image(LOGO_URL, width=140)
st.title("H DECANTS — Gestión de Pedidos")

# =====================
# CLIENTE GSHEETS
# =====================
@st.cache_resource(show_spinner=False)
def get_client_and_ws():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["GOOGLE_SERVICE_ACCOUNT"], scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL)
    productos_ws = sheet.worksheet(SHEET_TAB_PRODUCTOS)
    pedidos_ws = sheet.worksheet(SHEET_TAB_PEDIDOS)
    envios_ws = sheet.worksheet(SHEET_TAB_ENVIOS)
    return client, sheet, productos_ws, pedidos_ws, envios_ws

client, sheet, productos_ws, pedidos_ws, envios_ws = get_client_and_ws()

# =====================
# CARGA / GUARDA DATOS
# =====================
@st.cache_data(ttl=60, show_spinner=False)
def load_productos_df() -> pd.DataFrame:
    df = pd.DataFrame(productos_ws.get_all_records())
    if df.empty:
        return pd.DataFrame(columns=["Producto", "Costo x ml", "Stock disponible"])
    if "Costo x ml" in df:
        df["Costo x ml"] = pd.to_numeric(df["Costo x ml"], errors="coerce").fillna(0.0)
    if "Stock disponible" in df:
        df["Stock disponible"] = pd.to_numeric(df["Stock disponible"], errors="coerce").fillna(0)
    return df

@st.cache_data(ttl=60, show_spinner=False)
def load_pedidos_df() -> pd.DataFrame:
    df = pd.DataFrame(pedidos_ws.get_all_records())
    if df.empty:
        return pd.DataFrame(columns=["# Pedido","Nombre Cliente","Fecha","Producto","Mililitros","Costo x ml","Total","Estatus"])
    for col in ["# Pedido", "Mililitros"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["Costo x ml","Total"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df

def save_productos_df(df: pd.DataFrame):
    productos_ws.clear()
    productos_ws.update([df.columns.tolist()] + df.fillna("").values.tolist())
    load_productos_df.clear()

def save_pedidos_df(df: pd.DataFrame):
    pedidos_ws.clear()
    pedidos_ws.update([df.columns.tolist()] + df.fillna("").values.tolist())
    load_pedidos_df.clear()

def append_envio_row(data: List):
    envios_ws.append_row(data)

# =====================
# UTILIDADES
# =====================
def next_pedido_id(pedidos_df: pd.DataFrame) -> int:
    if pedidos_df.empty or "# Pedido" not in pedidos_df.columns:
        return 1
    return int(pd.to_numeric(pedidos_df["# Pedido"], errors="coerce").fillna(0).max()) + 1

def generar_pdf(pedido_id: int, cliente: str, fecha: str, estatus: str,
                productos: List[Tuple[str, float, float, float]]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    try:
        pdf.image("hdecants_logo.jpg", x=160, y=8, w=30)
    except:
        pass

    # Fuente con soporte para acentos/emojis
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", "", 14)

    pdf.cell(0, 10, f"Pedido #{pedido_id}", ln=True)
    pdf.set_font("DejaVu", "", 12)
    pdf.cell(0, 8, f"👤 Cliente: {cliente}", ln=True)
    pdf.cell(0, 8, f"📅 Fecha: {fecha}", ln=True)
    pdf.cell(0, 8, f"📌 Estatus: {estatus}", ln=True)
    pdf.ln(6)

    # Tabla encabezados
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(80, 9, "Producto", 1)
    pdf.cell(25, 9, "ML", 1, 0, "C")
    pdf.cell(35, 9, "Costo/ml", 1, 0, "C")
    pdf.cell(35, 9, "Total", 1, 1, "C")

    total_general = 0.0
    pdf.set_font("DejaVu", "", 11)
    for nombre, ml, costo, total in productos:
        total_general += float(total or 0.0)
        pdf.cell(80, 8, str(nombre)[:42], 1)
        pdf.cell(25, 8, f"{ml:g}", 1, 0, "C")
        pdf.cell(35, 8, f"${costo:.2f}", 1, 0, "R")
        pdf.cell(35, 8, f"${total:.2f}", 1, 1, "R")

    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(140, 9, "TOTAL GENERAL", 1, 0, "R")
    pdf.cell(35, 9, f"${total_general:.2f}", 1, 1, "R")

    pdf.ln(12)
    pdf.set_font("DejaVu", "", 11)
    pdf.multi_cell(0, 8,
        "💳 Una vez confirmada la cotización, realice el pago a la cuenta:\n\n"
        "4815163203579563\n"
        "BBVA\n"
        "Harim Escalona\n\n"
        "✅ Una vez confirmado el pago se procede a realizar el pedido."
    )

    return pdf.output(dest="S").encode("latin1")

def link_pdf(bytes_pdf: bytes, filename: str) -> str:
    b64 = base64.b64encode(bytes_pdf).decode("utf-8")
    return f'<a href="data:application/pdf;base64,{b64}" target="_blank">📄 Ver PDF</a>', b64

def ensure_session_keys():
    st.session_state.setdefault("pedido_items", [])
    st.session_state.setdefault("nueva_sesion", False)

ensure_session_keys()

# =====================
# DATOS INICIALES
# =====================
productos_df = load_productos_df()
pedidos_df = load_pedidos_df()
pedido_id = next_pedido_id(pedidos_df)

# =====================
# TABS
# =====================
tab1, tab2, tab3 = st.tabs(["➕ Nuevo Pedido", "📋 Historial", "🧪 Productos"])

# =====================
# TAB 1: NUEVO PEDIDO
# =====================
with tab1:
    if st.session_state.get("nueva_sesion", False):
        st.session_state.pedido_items = []
        st.session_state.nueva_sesion = False

    with st.form("form_pedido", clear_on_submit=False):
        col_a, col_b, col_c = st.columns([3,1.5,1.5])
        with col_a:
            cliente = st.text_input("👤 Cliente", placeholder="Nombre y apellidos")
        with col_b:
            fecha = st.date_input("📅 Fecha", value=datetime.today().date())
        with col_c:
            estatus = st.selectbox("📌 Estatus", ESTATUS_LIST, index=0)

        st.markdown("### 🧴 Productos")
        c1, c2, c3, c4 = st.columns([3,1.2,1.2,0.8])
        with c1:
            search = st.text_input("Buscar producto", placeholder="Escribe parte del nombre")
            opciones = productos_df[productos_df["Producto"].str.contains(search, case=False, na=False)] if search else productos_df
            prod_sel = st.selectbox("Producto", opciones["Producto"].tolist() or ["—"], index=0)
        with c2:
            ml = st.number_input("ML", min_value=0.0, step=0.5, value=0.0)
        with c3:
            costo_actual = float(productos_df.loc[productos_df["Producto"]==prod_sel, "Costo x ml"].iloc[0]) if prod_sel in productos_df["Producto"].values else 0.0
            st.number_input("Costo/ml (ref)", value=float(costo_actual), disabled=True)
        with c4:
            st.write("")
            add = st.form_submit_button("➕ Agregar")

        if add:
            if not prod_sel or prod_sel == "—":
                st.warning("Seleccione un producto válido.")
            elif ml <= 0:
                st.warning("Indique mililitros > 0.")
            else:
                stock_disp = float(productos_df.loc[productos_df["Producto"]==prod_sel, "Stock disponible"].iloc[0])
                if ml > stock_disp:
                    st.error(f"Stock insuficiente. Disponible: {stock_disp:g} ml")
                else:
                    total = ml * costo_actual
                    st.session_state.pedido_items.append((prod_sel, ml, costo_actual, total))

        if st.session_state.pedido_items:
            st.markdown("#### Carrito del Pedido")
            cart_df = pd.DataFrame(st.session_state.pedido_items, columns=["Producto","ML","Costo x ml","Total"])
            st.dataframe(cart_df, use_container_width=True, height=min(360, 36*(len(cart_df)+1)))
            total_general = float(cart_df["Total"].sum())
            st.metric("Total del pedido", f"${total_general:,.2f}")

        submitted = st.form_submit_button("💾 Guardar Pedido", type="primary")

    if submitted:
        if not cliente.strip():
            st.error("Ingrese el nombre del cliente.")
        elif not st.session_state.pedido_items:
            st.error("Agregue al menos un producto.")
        else:
            nuevas_filas = []
            for prod, ml_val, costo_val, total_val in st.session_state.pedido_items:
                nuevas_filas.append({
                    "# Pedido": pedido_id,
                    "Nombre Cliente": cliente.strip(),
                    "Fecha": fecha.strftime("%Y-%m-%d"),
                    "Producto": prod,
                    "Mililitros": float(ml_val),
                    "Costo x ml": float(costo_val),
                    "Total": float(total_val),
                    "Estatus": estatus
                })
                idx = productos_df.index[productos_df["Producto"]==prod][0]
                productos_df.at[idx, "Stock disponible"] -= float(ml_val)

            pedidos_df_new = pd.concat([pedidos_df, pd.DataFrame(nuevas_filas)], ignore_index=True)
            save_pedidos_df(pedidos_df_new)
            save_productos_df(productos_df)

            st.success(f"Pedido #{pedido_id} guardado.")
            pdf_bytes = generar_pdf(pedido_id, cliente.strip(), fecha.strftime("%Y-%m-%d"), estatus, st.session_state.pedido_items)
            link, b64 = link_pdf(pdf_bytes, f"Pedido_{pedido_id}_{cliente.replace(' ','')}.pdf")
            st.markdown(link, unsafe_allow_html=True)
            st.download_button("⬇️ Descargar PDF", pdf_bytes, file_name=f"Pedido_{pedido_id}_{cliente.replace(' ','')}.pdf", mime="application/pdf")

            st.session_state.pedido_items = []
            st.session_state.nueva_sesion = True
            st.rerun()

# =====================
# FOOTER
# =====================
st.caption("v3 — Flujo de pedidos con PDF y leyenda de pago incluida.")