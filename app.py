
# app_decants_final_completo_sin_duplicados.py — Versión corregida (una sola barra de navegación)

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


# === UI PRINCIPAL ===
st.set_page_config(page_title="App Decants", layout="centered")
st.image("https://raw.githubusercontent.com/HarimEG/app-decants/072576bfb6326d13c6528c7723e8b4f85c2abc65/hdecants_logo.jpg", width=150)
st.title("H DECANTS Pedidos")

productos_df = cargar_productos()
pedidos_df = cargar_pedidos()
pedido_id = int(pedidos_df["# Pedido"].max()) + 1 if not pedidos_df.empty else 1

# === TABS ===
tab1, tab2, tab3 = st.tabs(["➕ Nuevo Pedido", "📋 Historial de Pedidos", "🧪 Nuevo Producto"])

# === TAB 1 ===
with tab1:
    with st.form("formulario"):
        cliente = st.text_input("👤 Nombre del Cliente")
        fecha = st.date_input("📅 Fecha del pedido", value=datetime.today())
        estatus = st.selectbox("📌 Estatus", ["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"])

        requiere_envio = st.checkbox("¿Requiere envío?")
        datos_envio = []
        if requiere_envio:
            with st.expander("📦 Datos de envío", expanded=False):
                nombre_dest = st.text_input("Destinatario")
                calle = st.text_input("Calle y número")
                colonia = st.text_input("Colonia")
                cp = st.text_input("Código Postal")
                ciudad = st.text_input("Ciudad")
                estado = st.text_input("Estado")
                telefono = st.text_input("Teléfono")
                referencia = st.text_area("Referencia")
                datos_envio = [pedido_id, cliente, nombre_dest, calle, colonia, cp, ciudad, estado, telefono, referencia]

        st.subheader("🧴 Productos")
        col1, col2 = st.columns(2)
        with col1:
            search_term = st.text_input("Buscar producto")
            opciones_filtradas = productos_df[productos_df["Producto"].str.contains(search_term, case=False, na=False)]["Producto"].tolist()
            producto = st.selectbox("Producto", opciones_filtradas if opciones_filtradas else ["Ningún resultado"])
        with col2:
            ml = st.number_input("Mililitros", min_value=0, step=1)

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

        if requiere_envio and datos_envio:
            guardar_envio(datos_envio)

        st.success(f"Pedido #{pedido_id} guardado correctamente")
        pdf_bytes = generar_pdf(pedido_id, cliente, fecha.strftime("%Y-%m-%d"), estatus, st.session_state.productos)
        b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        st.markdown(f'<a href="data:application/pdf;base64,{b64_pdf}" target="_blank">📄 Ver PDF</a>', unsafe_allow_html=True)
        st.download_button("⬇️ Descargar PDF", pdf_bytes, f"Pedido_{pedido_id}_{cliente.replace(' ', '')}.pdf", mime="application/pdf")
        if st.button("🔁 Registrar otro pedido"):
            st.session_state.productos = []
            st.rerun()




# === TAB 2: Historial editable ===
with tab2:
    st.subheader("📋 Historial de Pedidos por Cliente")
    nombre_cliente_filtro = st.text_input("🔍 Buscar cliente")

    if nombre_cliente_filtro:
        pedidos_filtrados = pedidos_df[pedidos_df["Nombre Cliente"].str.contains(nombre_cliente_filtro, case=False, na=False)]
    else:
        pedidos_filtrados = pedidos_df

    st.dataframe(pedidos_filtrados, use_container_width=True)

    if not pedidos_filtrados.empty:
        pedido_ids = pedidos_filtrados["# Pedido"].unique().tolist()
        pedido_id_sel = st.selectbox("Selecciona un pedido para editar/clonar", pedido_ids)
        pedido_seleccionado = pedidos_df[pedidos_df["# Pedido"] == pedido_id_sel]

        if not pedido_seleccionado.empty:
            st.markdown("### ✏️ Editar Pedido")

            nuevo_estatus = st.selectbox("Nuevo Estatus", ["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"],
                                          index=["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"].index(
                                              pedido_seleccionado["Estatus"].iloc[-1]
                                          ))

            st.markdown("#### Productos del pedido:")
            productos_pedido = pedido_seleccionado.reset_index()

            for i, row in productos_pedido.iterrows():
                cols = st.columns([3, 2, 2, 2, 1, 1])
                cols[0].write(row["Producto"])
                ml_edit = cols[1].number_input(f"Mililitros (Producto {i})", min_value=0.0, step=0.5,
                                               value=float(row["Mililitros"]), key=f"ml_{i}")
                cols[2].write(f"${row['Costo x ml']:.2f}")
                cols[3].write(f"${row['Total']:.2f}")

                if cols[4].button("✏️", key=f"update_{i}"):
                    diferencia_ml = ml_edit - row["Mililitros"]
                    idx_prod = productos_df[productos_df["Producto"] == row["Producto"]].index[0]
                    if diferencia_ml > productos_df.at[idx_prod, "Stock disponible"]:
                        st.error("No hay stock suficiente para aumentar la cantidad.")
                    else:
                        productos_df.at[idx_prod, "Stock disponible"] -= diferencia_ml
                        pedidos_df.at[row["index"], "Mililitros"] = ml_edit
                        pedidos_df.at[row["index"], "Total"] = ml_edit * row["Costo x ml"]
                        guardar_pedidos(pedidos_df)
                        guardar_productos(productos_df)
                        st.success(f"Cantidad de '{row['Producto']}' actualizada.")

                if cols[5].button("🗑️", key=f"delete_{i}"):
                    idx_prod = productos_df[productos_df["Producto"] == row["Producto"]].index[0]
                    productos_df.at[idx_prod, "Stock disponible"] += row["Mililitros"]
                    pedidos_df = pedidos_df.drop(pedidos_df[
                        (pedidos_df["# Pedido"] == pedido_id_sel) &
                        (pedidos_df["Producto"] == row["Producto"]) &
                        (pedidos_df["Mililitros"] == row["Mililitros"])
                    ].index)
                    guardar_pedidos(pedidos_df)
                    guardar_productos(productos_df)
                    st.success(f"Producto '{row['Producto']}' eliminado del pedido.")
                    st.experimental_rerun()

            st.markdown("#### ➕ Agregar nuevo producto al pedido")
            col1, col2 = st.columns(2)
            with col1:
                search_term_edit = st.text_input("Buscar producto nuevo", key="search_nuevo")
                opciones_nuevas = productos_df[productos_df["Producto"].str.contains(search_term_edit, case=False, na=False)]["Producto"].tolist()
                nuevo_producto = st.selectbox("Producto", opciones_nuevas if opciones_nuevas else ["Ningún resultado"], key="nuevo_producto_sel")
            with col2:
                nuevo_ml = st.number_input("Mililitros", min_value=0.0, step=0.5, key="nuevo_ml")

            if st.button("Agregar nuevo producto al pedido"):
                fila_nueva = productos_df[productos_df["Producto"] == nuevo_producto]
                if not fila_nueva.empty:
                    idx = fila_nueva.index[0]
                    costo = float(fila_nueva["Costo x ml"].values[0])
                    total = nuevo_ml * costo

                    if nuevo_ml > productos_df.at[idx, "Stock disponible"]:
                        st.error("No hay stock suficiente para agregar este producto.")
                    else:
                        productos_df.at[idx, "Stock disponible"] -= nuevo_ml
                        nuevo_registro = {
                            "# Pedido": pedido_id_sel,
                            "Nombre Cliente": pedido_seleccionado["Nombre Cliente"].iloc[0],
                            "Fecha": pedido_seleccionado["Fecha"].iloc[0],
                            "Producto": nuevo_producto,
                            "Mililitros": nuevo_ml,
                            "Costo x ml": costo,
                            "Total": total,
                            "Estatus": pedido_seleccionado["Estatus"].iloc[-1]
                        }
                        pedidos_df = pd.concat([pedidos_df, pd.DataFrame([nuevo_registro])], ignore_index=True)
                        guardar_pedidos(pedidos_df)
                        guardar_productos(productos_df)
                        st.success(f"Producto '{nuevo_producto}' agregado al pedido.")
                        st.experimental_rerun()

            if st.button("Actualizar Estatus del Pedido"):
                pedidos_df.loc[pedidos_df["# Pedido"] == pedido_id_sel, "Estatus"] = nuevo_estatus
                guardar_pedidos(pedidos_df)
                st.success("✅ Estatus actualizado.")


 #Agregar nuevo producto ===
with tab3:
    st.subheader("🧪 Agregar nuevo perfume")
    with st.form("form_nuevo_producto"):
        nombre_producto = st.text_input("Nombre del producto")
        costo_ml = st.number_input("Costo por ml", min_value=0.0, step=0.1)
        stock_inicial = st.number_input("Stock disponible (ml)", min_value=0, step=1)
        submit_producto = st.form_submit_button("➕ Agregar")

        if submit_producto:
            if nombre_producto.strip() == "" or costo_ml <= 0:
                st.error("Completa todos los campos correctamente.")
            else:
                nuevo = pd.DataFrame([{
                    "Producto": nombre_producto.strip(),
                    "Costo x ml": costo_ml,
                    "Stock disponible": stock_inicial
                }])
                productos_df = pd.concat([productos_df, nuevo], ignore_index=True)
                guardar_productos(productos_df)
                st.success(f"Producto '{nombre_producto}' agregado correctamente.")
