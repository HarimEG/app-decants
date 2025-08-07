
# app_decants_final.py — Versión completa e integrada para Streamlit + iPhone
# Autor: Harim Escalona
# Descripción: Gestión de pedidos, productos, envíos y generación de PDFs con integración a Google Sheets.

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
from datetime import datetime
import base64

# === Autenticación Google Sheets ===
scope = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(st.secrets["GOOGLE_SERVICE_ACCOUNT"], scopes=scope)
client = gspread.authorize(creds)

# === URLs de hojas
SHEET_URL = "https://docs.google.com/spreadsheets/d/1bjV4EaDNNbJfN4huzbNpTFmj-vfCr7A2474jhO81-bE/edit?gid=1318862509#gid=1318862509"
sheet = client.open_by_url(SHEET_URL)
productos_ws = sheet.worksheet("Productos")
pedidos_ws = sheet.worksheet("Pedidos")
envios_ws = sheet.worksheet("Envios")

# === Funciones ===
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

def guardar_envio(data):
    envios_ws.append_row(data)

def generar_pdf(pedido_id, cliente, fecha, estatus, productos):
    pdf = FPDF()
    pdf.add_page()
    pdf.image("hdecants_logo.jpg", x=160, y=8, w=30)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Pedido #{pedido_id}", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Cliente: {cliente}", ln=True)
    pdf.cell(0, 10, f"Fecha: {fecha}", ln=True)
    pdf.cell(0, 10, f"Estatus: {estatus}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(60, 10, "Producto", 1)
    pdf.cell(30, 10, "ML", 1)
    pdf.cell(30, 10, "Costo", 1)
    pdf.cell(30, 10, "Total", 1)
    pdf.ln()

    total_general = 0
    pdf.set_font("Arial", size=12)
    for p in productos:
        total_general += p[3]
        pdf.cell(60, 10, p[0], 1)
        pdf.cell(30, 10, str(p[1]), 1)
        pdf.cell(30, 10, f"${p[2]:.2f}", 1)
        pdf.cell(30, 10, f"${p[3]:.2f}", 1)
        pdf.ln()

    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(120, 10, "TOTAL GENERAL", 1, 0, 'R', fill=True)
    pdf.cell(30, 10, f"${total_general:.2f}", 1, 1, 'C', fill=True)
    return pdf.output(dest='S').encode('latin1')


st.set_page_config(page_title="App Decants", layout="centered")
st.image("https://raw.githubusercontent.com/HarimEG/app-decants/072576bfb6326d13c6528c7723e8b4f85c2abc65/hdecants_logo.jpg", width=150)
st.title("H DECANTS Pedidos")

productos_df = cargar_productos()
pedidos_df = cargar_pedidos()
pedido_id = int(pedidos_df["# Pedido"].max()) + 1 if not pedidos_df.empty else 1

tab1, tab2, tab3 = st.tabs(["➕ Nuevo Pedido", "📋 Historial de Pedidos", "🧪 Nuevo Producto"])


# === TAB 3 ===

# app_optimizado.py — Versión extendida con pestaña para gestionar productos

# (Este archivo extiende lo que ya tienes: mantiene 'Nuevo Pedido', 'Historial',
#  y agrega una pestaña llamada '🧪 Nuevo Producto')

# Dentro de tu app_optimizado.py añade una nueva pestaña así:

tab1, tab2, tab3 = st.tabs(["➕ Nuevo Pedido", "📋 Historial de Pedidos", "🧪 Nuevo Producto"])

# === TAB 3: Agregar nuevo producto a la base de datos ===
with tab3:
    st.subheader("📦 Registrar nuevo producto")
    with st.form("form_nuevo_producto"):
        nombre_producto = st.text_input("Nombre del producto")
        costo_ml = st.number_input("Costo por ml", min_value=0.0, step=0.1)
        stock_inicial = st.number_input("Stock disponible (ml)", min_value=0, step=1)
        submit_producto = st.form_submit_button("➕ Agregar producto")

        if submit_producto:
            if nombre_producto.strip() == "" or costo_ml <= 0:
                st.error("Por favor completa todos los campos correctamente.")
            else:
                nuevo = pd.DataFrame([{
                    "Producto": nombre_producto.strip(),
                    "Costo x ml": costo_ml,
                    "Stock disponible": stock_inicial
                }])
                productos_df = pd.concat([productos_df, nuevo], ignore_index=True)
                guardar_productos(productos_df)
                st.success(f"Producto '{nombre_producto}' agregado correctamente.")


# === TAB 2 - Clonación avanzada ===

# 🔁 Clonar pedido con control de stock y generación automática de PDF

if st.button("🔁 Clonar Pedido"):
    productos_originales = pedido_seleccionado[["Producto", "Mililitros", "Costo x ml", "Total"]].values.tolist()
    nuevo_id = int(pedidos_df["# Pedido"].max()) + 1
    nueva_fecha = datetime.today().strftime("%Y-%m-%d")
    cliente = pedido_seleccionado["Nombre Cliente"].iloc[0]
    estatus = "Cotizacion"

    nuevos_registros = []
    errores_stock = []

    for p in productos_originales:
        producto, ml, costo, total = p
        idx = productos_df[productos_df["Producto"] == producto].index

        if not idx.empty:
            idx = idx[0]
            if productos_df.at[idx, "Stock disponible"] >= ml:
                productos_df.at[idx, "Stock disponible"] -= ml
                nuevos_registros.append({
                    "# Pedido": nuevo_id,
                    "Nombre Cliente": cliente,
                    "Fecha": nueva_fecha,
                    "Producto": producto,
                    "Mililitros": ml,
                    "Costo x ml": costo,
                    "Total": total,
                    "Estatus": estatus
                })
            else:
                errores_stock.append(producto)
        else:
            errores_stock.append(producto)

    if nuevos_registros:
        pedidos_df = pd.concat([pedidos_df, pd.DataFrame(nuevos_registros)], ignore_index=True)
        guardar_pedidos(pedidos_df)
        guardar_productos(productos_df)

        st.success(f"✅ Pedido #{nuevo_id} clonado exitosamente.")

        # Generar PDF automáticamente
        pdf_bytes = generar_pdf(nuevo_id, cliente, nueva_fecha, estatus, productos_originales)
        b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')

        st.markdown(f'<a href="data:application/pdf;base64,{b64_pdf}" target="_blank">📄 Ver PDF del nuevo pedido</a>', unsafe_allow_html=True)
        st.download_button(
            label="⬇️ Descargar PDF del nuevo pedido",
            data=pdf_bytes,
            file_name=f"Pedido_{nuevo_id}_{cliente.replace(' ', '')}.pdf",
            mime="application/pdf"
        )

    if errores_stock:
        st.warning("⚠️ Los siguientes productos no se clonaron por falta de stock: " + ", ".join(errores_stock))

    st.rerun()