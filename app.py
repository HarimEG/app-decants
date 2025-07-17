# app.py (versión Streamlit para usar desde tu iPhone)

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
from datetime import datetime
import os
import io
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

    pdf.set_draw_color(0, 0, 0)
    pdf.line(10, pdf.get_y(), 190, pdf.get_y())

    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(120, 10, "TOTAL GENERAL", 1, 0, 'R', fill=True)
    pdf.cell(30, 10, f"${total_general:.2f}", 1, 1, 'C', fill=True)

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    return pdf_bytes


def mostrar_historial_y_editar():
    st.subheader("📋 Historial de Pedidos por Cliente")
    pedidos_df = cargar_pedidos()
    productos_df = cargar_productos()

    nombre_filtrar = st.text_input("Buscar por nombre del cliente")
    pedidos_filtrados = pedidos_df[pedidos_df["Nombre Cliente"].str.contains(nombre_filtrar, case=False, na=False)]

    st.dataframe(pedidos_filtrados, use_container_width=True)

    if not pedidos_filtrados.empty:
        pedido_id_sel = st.selectbox("Selecciona un pedido para editar", sorted(pedidos_filtrados["# Pedido"].unique()))

        if pedido_id_sel:
            pedido_actual = pedidos_df[pedidos_df["# Pedido"] == pedido_id_sel]
            st.markdown(f"### ✏️ Editar Pedido #{pedido_id_sel}")

            for i, row in pedido_actual.iterrows():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"{row['Producto']} - {row['Mililitros']}ml - ${row['Total']:.2f}")
                with col2:
                    eliminar = st.button("🗑️", key=f"eliminar_{i}")
                    if eliminar:
                        pedidos_df = pedidos_df.drop(i)
                        idx = productos_df[productos_df["Producto"] == row["Producto"].strip()].index[0]
                        productos_df.at[idx, "Stock disponible"] += row["Mililitros"]
                        guardar_pedidos(pedidos_df)
                        guardar_productos(productos_df)
                        st.experimental_rerun()

            nuevo_estatus = st.selectbox("Actualizar Estatus", ["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"],
                                          index=["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"].index(
                                              pedido_actual["Estatus"].iloc[-1]))

            if st.button("Actualizar Estatus del Pedido"):
                pedidos_df.loc[pedidos_df["# Pedido"] == pedido_id_sel, "Estatus"] = nuevo_estatus
                guardar_pedidos(pedidos_df)
                st.success("✅ Estatus actualizado.")

mostrar_historial_y_editar()

