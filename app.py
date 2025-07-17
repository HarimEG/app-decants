# app.py (versión Streamlit para usar desde tu iPhone)

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

    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(120, 10, "TOTAL GENERAL", 1, 0, 'R', fill=True)
    pdf.cell(30, 10, f"${total_general:.2f}", 1, 1, 'C', fill=True)

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    return pdf_bytes

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
        search_term = st.text_input("Buscar producto")
        opciones_filtradas = productos_df[productos_df["Producto"].str.contains(search_term, case=False, na=False)]["Producto"].tolist()
        producto = st.selectbox("Producto", opciones_filtradas if opciones_filtradas else ["Ningún resultado"])
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
    b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    href = f'<a href="data:application/pdf;base64,{b64_pdf}" target="_blank">Ver PDF en nueva pestaña</a>'
    st.markdown(href, unsafe_allow_html=True)

    st.download_button(
        label="⬇️ Descargar PDF del pedido",
        data=pdf_bytes,
        file_name=f"Pedido_{pedido_id}_{cliente.replace(' ', '')}.pdf",
        mime="application/pdf"
    )

    st.markdown("---")
    if st.button("🔁 Registrar otro pedido"):
        st.session_state.productos = []
        st.session_state.pedido_guardado = False
        st.rerun()

# === Historial y Edición ===
st.subheader("📋 Historial de Pedidos por Cliente")
nombre_cliente_filtro = st.text_input("Buscar cliente por nombre")

if nombre_cliente_filtro:
    pedidos_filtrados = pedidos_df[pedidos_df["Nombre Cliente"].str.contains(nombre_cliente_filtro, case=False, na=False)]
else:
    pedidos_filtrados = pedidos_df

st.dataframe(pedidos_filtrados, use_container_width=True)

if not pedidos_filtrados.empty:
    pedido_ids = pedidos_filtrados["# Pedido"].unique().tolist()
    pedido_id_sel = st.selectbox("Selecciona un pedido para editar", pedido_ids)

    pedido_seleccionado = pedidos_df[pedidos_df["# Pedido"] == pedido_id_sel]

    if not pedido_seleccionado.empty:
        with st.expander(f"✏️ Editar Pedido #{pedido_id_sel}"):
            nuevo_estatus = st.selectbox("Nuevo Estatus", 
                                         ["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"], 
                                         index=["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"].index(
                                             pedido_seleccionado["Estatus"].iloc[-1]
                                         ))

            buscar_nombre = st.text_input("🔍 Buscar producto por nombre")
            productos_filtrados = productos_df[productos_df["Producto"].str.contains(buscar_nombre, case=False, na=False)]

            if not productos_filtrados.empty:
                nuevo_producto = st.selectbox("Selecciona producto", productos_filtrados["Producto"].tolist())
                nuevo_ml = st.number_input("Mililitros a agregar", min_value=0.0, step=1.0)

                if st.button("Agregar Producto al Pedido"):
                    costo = float(productos_df.loc[productos_df["Producto"] == nuevo_producto, "Costo x ml"].values[0])
                    total = nuevo_ml * costo

                    nueva_fila = {
                        "# Pedido": pedido_id_sel,
                        "Nombre Cliente": pedido_seleccionado["Nombre Cliente"].iloc[0],
                        "Fecha": pedido_seleccionado["Fecha"].iloc[0],
                        "Producto": nuevo_producto,
                        "Mililitros": nuevo_ml,
                        "Costo x ml": costo,
                        "Total": total,
                        "Estatus": nuevo_estatus
                    }

                    pedidos_df = pd.concat([pedidos_df, pd.DataFrame([nueva_fila])], ignore_index=True)

                    idx = productos_df[productos_df["Producto"] == nuevo_producto].index[0]
                    productos_df.at[idx, "Stock disponible"] -= nuevo_ml

                    guardar_pedidos(pedidos_df)
                    guardar_productos(productos_df)

                    st.success("✅ Producto agregado correctamente.")

            if st.button("Actualizar Estatus del Pedido"):
                pedidos_df.loc[pedidos_df["# Pedido"] == pedido_id_sel, "Estatus"] = nuevo_estatus
                guardar_pedidos(pedidos_df)
                st.success("✅ Estatus actualizado.")

            if st.button("📄 Generar PDF actualizado"):
                productos_actualizados = pedidos_df[pedidos_df["# Pedido"] == pedido_id_sel][["Producto", "Mililitros", "Costo x ml", "Total"]].values.tolist()
                cliente_pdf = pedido_seleccionado["Nombre Cliente"].iloc[0]
                fecha_pdf = pedido_seleccionado["Fecha"].iloc[0]
                estatus_pdf = pedidos_df[pedidos_df["# Pedido"] == pedido_id_sel]["Estatus"].iloc[-1]

                pdf_bytes = generar_pdf(pedido_id_sel, cliente_pdf, fecha_pdf, estatus_pdf, productos_actualizados)
                st.download_button(
                    label="📥 Descargar PDF del pedido actualizado",
                    data=pdf_bytes,
                    file_name=f"Pedido_{pedido_id_sel}_{cliente_pdf.replace(' ', '')}.pdf",
                    mime="application/pdf"
                )
