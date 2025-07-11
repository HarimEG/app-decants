
# app.py (versión Streamlit para usar desde tu iPhone)

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
from datetime import datetime
import os
import io

# === Autenticación Google Sheets ===
scope = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(st.secrets["GOOGLE_SERVICE_ACCOUNT"], scopes=scope)
client = gspread.authorize(creds)

# === URLs de hojas
SHEET_URL = "https://docs.google.com/spreadsheets/d/1bjV4EaDNNbJfN4huzbNpTFmj-vfCr7A2474jhO81-bE/edit?gid=1318862509#gid=1318862509"
sheet = client.open_by_url(SHEET_URL)
productos_ws = sheet.worksheet("Productos")
pedidos_ws = sheet.worksheet("Pedidos")

# === Cargar datos ===
def cargar_productos():
    return pd.DataFrame(productos_ws.get_all_records())

def cargar_pedidos():
    return pd.DataFrame(pedidos_ws.get_all_records())

def guardar_productos(df):
    productos_ws.clear()
    productos_ws.update([df.columns.tolist()] + df.values.tolist())

def guardar_pedidos(df):
    pedidos_ws.clear()
    pedidos_ws.update([df.columns.tolist()] + df.values.tolist())

# === PDF ===
import requests

import requests

def generar_pdf(pedido_id, cliente, fecha, estatus, productos):
    pdf = FPDF()
    pdf.add_page()

    # === Logo (arriba derecha) ===
    logo_url = "https://raw.githubusercontent.com/HarimEG/app-decants/main/hdecants_logo.jpg"
    response = requests.get(logo_url)
    if response.status_code == 200:
        with open("temp_logo.jpg", "wb") as f:
            f.write(response.content)
        pdf.image("temp_logo.jpg", x=160, y=10, w=40)
        os.remove("temp_logo.jpg")

    # === Encabezado ===
    pdf.set_xy(10, 15)
    pdf.set_font("Arial", "B", 16)
    pdf.cell(100, 10, f"PEDIDO #{pedido_id}", ln=True)

    pdf.set_font("Arial", "", 12)
    pdf.cell(100, 8, f"Cliente: {cliente}", ln=True)
    pdf.cell(100, 8, f"Fecha: {fecha}", ln=True)
    pdf.cell(100, 8, f"Estatus: {estatus}", ln=True)
    pdf.ln(10)

    # === Tabla de productos ===
    pdf.set_font("Arial", "B", 12)
    pdf.cell(70, 10, "Producto", 1)
    pdf.cell(25, 10, "ML", 1)
    pdf.cell(30, 10, "Costo x ML", 1)
    pdf.cell(30, 10, "Total", 1)
    pdf.ln()

    total_general = 0
    pdf.set_font("Arial", "", 12)
    for producto, ml, costo, total in productos:
        total_general += total
        pdf.cell(70, 10, producto, 1)
        pdf.cell(25, 10, f"{ml:.1f}", 1)
        pdf.cell(30, 10, f"${costo:.2f}", 1)
        pdf.cell(30, 10, f"${total:.2f}", 1)
        pdf.ln()

    # === Total general ===
    pdf.set_font("Arial", "B", 12)
    pdf.cell(125, 10, "TOTAL GENERAL", 1)
    pdf.cell(30, 10, f"${total_general:.2f}", 1)
    pdf.ln(15)

    # === Footer opcional (puedes personalizarlo) ===
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "Gracias por tu compra. H DECANTS", ln=True, align="C")

    return pdf.output(dest="S").encode("latin1")


# === Streamlit App ===
st.set_page_config(page_title="App Decants", layout="centered")
st.title("H DECANTS Pedidos")
st.image("https://raw.githubusercontent.com/HarimEG/app-decants/072576bfb6326d13c6528c7723e8b4f85c2abc65/hdecants_logo.jpg", width=150)
productos_df = cargar_productos()
pedidos_df = cargar_pedidos()
pedido_id = int(pedidos_df["# Pedido"].max()) + 1 if not pedidos_df.empty else 1


with st.form("formulario"):
    cliente = st.text_input("Nombre del Cliente")
    fecha = st.date_input("Fecha del pedido", value=datetime.today())
    estatus = st.selectbox("Estatus", ["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"])

    st.markdown("---")
    st.subheader("Agregar Productos")

    col1, col2 = st.columns(2)
    with col1:
        producto = st.selectbox("Producto", productos_df["Producto"].tolist())
    with col2:
        ml = st.number_input("Mililitros", min_value=0.0, step=1.0)

    agregar = st.form_submit_button("Agregar producto")

    if "productos" not in st.session_state:
        st.session_state.productos = []

    if agregar:
        fila = productos_df[productos_df["Producto"] == producto]
        if not fila.empty:
            costo = float(fila["Costo x ml"].values[0])
            total = ml * costo
            st.session_state.productos.append((producto, ml, costo, total))

    if st.session_state.productos:
        st.session_state.pedido_guardado = True
        st.markdown("### Productos en el pedido")
        st.table(pd.DataFrame(st.session_state.productos, columns=["Producto", "ML", "Costo", "Total"]))

    submit = st.form_submit_button("Guardar Pedido")

if submit and st.session_state.productos:
    nuevas_filas = []
    for prod, ml, costo, total in st.session_state.productos:
        nuevas_filas.append({
            "# Pedido": pedido_id,
            "Nombre Cliente": cliente,
            "Fecha": fecha.strftime("%Y-%m-%d"),
            "Producto": prod,
            "Mililitros": ml,
            "Costo x ml": costo,
            "Total": total,
            "Estatus": estatus
        })
        idx = productos_df[productos_df["Producto"] == prod].index[0]
        productos_df.at[idx, "Stock disponible"] -= ml

    df_nuevo = pd.concat([pedidos_df, pd.DataFrame(nuevas_filas)], ignore_index=True)
    guardar_pedidos(df_nuevo)
    guardar_productos(productos_df)

    st.success(f"Pedido #{pedido_id} guardado correctamente")

    pdf_bytes = generar_pdf(pedido_id, cliente, fecha.strftime("%Y-%m-%d"), estatus, st.session_state.productos)
    st.download_button(
        label="Descargar PDF del pedido",
        data=pdf_bytes,
        file_name=f"Pedido_{pedido_id}_{cliente.replace(' ', '')}.pdf",
        mime="application/pdf"
    )
    
    st.markdown("---")
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔁 Nuevo pedido"):
            st.session_state.productos = []
            st.session_state.pedido_guardado = False
            st.experimental_rerun()

    
    st.session_state.productos = []
