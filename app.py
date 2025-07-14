
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

import base64

def generar_pdf(pedido_id, cliente, fecha, estatus, productos):
    pdf = FPDF()
    pdf.add_page()

    # Logo arriba derecha (ajusta path o URL local)
    pdf.image("hdecants_logo.jpg", x=160, y=8, w=30)  

    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Pedido #{pedido_id}", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Cliente: {cliente}", ln=True)
    pdf.cell(0, 10, f"Fecha: {fecha}", ln=True)
    pdf.cell(0, 10, f"Estatus: {estatus}", ln=True)
    pdf.ln(10)

    # Tabla encabezado
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

    # Línea separadora antes del total
    pdf.set_draw_color(0, 0, 0)
    pdf.line(10, pdf.get_y(), 190, pdf.get_y())

    # Total general destacado con fondo gris claro
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(120, 10, "TOTAL GENERAL", 1, 0, 'R', fill=True)
    pdf.cell(30, 10, f"${total_general:.2f}", 1, 1, 'C', fill=True)

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    return pdf_bytes



def obtener_productos_pedido(pedido_id, df_pedidos):
    return df_pedidos[df_pedidos["# Pedido"] == pedido_id].copy()

def actualizar_stock(productos_df, productos_antes, productos_despues):
    # productos_antes y productos_despues tienen columnas: Producto, Mililitros
    for _, row in productos_antes.iterrows():
        prod = row["Producto"]
        ml = row["Mililitros"]
        idx = productos_df[productos_df["Producto"] == prod].index[0]
        productos_df.at[idx, "Stock disponible"] += ml  # devolver stock anterior

    for _, row in productos_despues.iterrows():
        prod = row["Producto"]
        ml = row["Mililitros"]
        idx = productos_df[productos_df["Producto"] == prod].index[0]
        productos_df.at[idx, "Stock disponible"] -= ml  # descontar nuevo stock

    return productos_df

def mostrar_historial_y_editar():
    global pedidos_df_global, productos_df_global

    st.header("Historial de Pedidos")

    nombre_filtro = st.text_input("Buscar cliente", key="buscar_cliente")
    if nombre_filtro:
        df_filtrado = pedidos_df_global[pedidos_df_global["Nombre Cliente"].str.contains(nombre_filtro, case=False, na=False)]
    else:
        df_filtrado = pedidos_df_global.copy()

    st.dataframe(df_filtrado)

    max_pedido = int(pedidos_df_global["# Pedido"].max()) if not pedidos_df_global.empty else 1
    pedido_seleccionado = st.number_input("Selecciona # Pedido para editar", min_value=1, max_value=max_pedido, step=1)

    if st.button("Editar Pedido"):
        with st.modal("Editar Pedido"):
            productos_pedido = obtener_productos_pedido(pedido_seleccionado, pedidos_df_global)
            if productos_pedido.empty:
                st.warning("Pedido no encontrado")
                return
            estatus_actual = productos_pedido["Estatus"].iloc[0]

            nuevo_estatus = st.selectbox(
                "Estatus", 
                ["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"], 
                index=["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"].index(estatus_actual)
            )

            st.write("### Productos actuales")
            edited_productos = []
            for i, row in productos_pedido.iterrows():
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.write(row["Producto"])
                with col2:
                    ml_nuevo = st.number_input(f"Mililitros para {row['Producto']}", value=row["Mililitros"], min_value=0.0, step=0.5, key=f"ml_{pedido_seleccionado}_{i}")
                with col3:
                    eliminar = st.checkbox(f"Eliminar", key=f"del_{pedido_seleccionado}_{i}")

                if not eliminar and ml_nuevo > 0:
                    costo = row["Costo x ml"]
                    total = ml_nuevo * costo
                    edited_productos.append({
                        "Producto": row["Producto"],
                        "Mililitros": ml_nuevo,
                        "Costo x ml": costo,
                        "Total": total
                    })

            st.write("### Agregar nuevos productos")
            productos_disponibles = productos_df_global[~productos_df_global["Producto"].isin([p["Producto"] for p in edited_productos])]
            if not productos_disponibles.empty:
                nuevo_producto = st.selectbox("Nuevo Producto", productos_disponibles["Producto"].tolist(), key="nuevo_producto")
                ml_nuevo_producto = st.number_input("Mililitros nuevo producto", min_value=0.0, step=0.5, key="ml_nuevo_producto")
                if ml_nuevo_producto > 0:
                    if st.button("Agregar producto al pedido", key="agregar_nuevo_producto"):
                        fila_prod = productos_df_global[productos_df_global["Producto"] == nuevo_producto].iloc[0]
                        costo = fila_prod["Costo x ml"]
                        total = ml_nuevo_producto * costo
                        edited_productos.append({
                            "Producto": nuevo_producto,
                            "Mililitros": ml_nuevo_producto,
                            "Costo x ml": costo,
                            "Total": total
                        })
                        st.experimental_rerun()
            else:
                st.info("No hay productos disponibles para agregar.")

            if st.button("Guardar Cambios en Pedido", key="guardar_cambios_pedido"):
                df_antes = productos_pedido[["Producto", "Mililitros"]]
                df_despues = pd.DataFrame(edited_productos)[["Producto", "Mililitros"]]

                # Validar stock
                for _, row in df_despues.iterrows():
                    prod = row["Producto"]
                    ml = row["Mililitros"]
                    stock_actual = productos_df_global.loc[productos_df_global["Producto"] == prod, "Stock disponible"].values[0]
                    stock_antes = df_antes.loc[df_antes["Producto"] == prod, "Mililitros"].values[0] if prod in df_antes["Producto"].values else 0
                    disponible = stock_actual + stock_antes  # stock + ml reservado previamente
                    if ml > disponible:
                        st.error(f"No hay suficiente stock para {prod}. Disponible: {disponible}, solicitado: {ml}")
                        return

                # Actualizar stock
                productos_df_global = actualizar_stock(productos_df_global, df_antes, df_despues)

                # Actualizar pedidos_df_global
                pedidos_df_global.drop(pedidos_df_global[pedidos_df_global["# Pedido"] == pedido_seleccionado].index, inplace=True)
                nuevas_filas = []
                cliente_nombre = productos_pedido["Nombre Cliente"].iloc[0]
                fecha_pedido = productos_pedido["Fecha"].iloc[0]
                for prod in edited_productos:
                    nuevas_filas.append({
                        "# Pedido": pedido_seleccionado,
                        "Nombre Cliente": cliente_nombre,
                        "Fecha": fecha_pedido,
                        "Producto": prod["Producto"],
                        "Mililitros": prod["Mililitros"],
                        "Costo x ml": prod["Costo x ml"],
                        "Total": prod["Total"],
                        "Estatus": nuevo_estatus
                    })

                pedidos_df_global = pd.concat([pedidos_df_global, pd.DataFrame(nuevas_filas)], ignore_index=True)

                guardar_productos(productos_df_global)
                guardar_pedidos(pedidos_df_global)

                st.success("Pedido actualizado correctamente")
                st.experimental_rerun()




# === Streamlit App ===
st.set_page_config(page_title="App Decants", layout="centered")
st.title("H DECANTS Pedidos")
st.image("https://raw.githubusercontent.com/HarimEG/app-decants/072576bfb6326d13c6528c7723e8b4f85c2abc65/hdecants_logo.jpg", width=150)
productos_df = cargar_productos()
pedidos_df = cargar_pedidos()
pedidos_df_global = pedidos_df.copy()
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

import base64  # Asegúrate de tener esto al inicio del script

# Generar el PDF
pdf_bytes = generar_pdf(pedido_id, cliente, fecha.strftime("%Y-%m-%d"), estatus, st.session_state.productos)

# Convertir a base64 para vista previa en navegador
b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')

# Mostrar enlace
href = f'<a href="data:application/pdf;base64,{b64_pdf}" target="_blank">Ver PDF en nueva pestaña</a>'
st.markdown(href, unsafe_allow_html=True)


# Ver PDF en navegador
st.markdown("### 📄 Vista previa del pedido")
href = f'<a href="data:application/pdf;base64,{b64_pdf}" target="_blank">Ver PDF en nueva pestaña</a>'
st.markdown(href, unsafe_allow_html=True)

# Botón para descarga
st.download_button(
    label="⬇️ Descargar PDF del pedido",
    data=pdf_bytes,
    file_name=f"Pedido_{pedido_id}_{cliente.replace(' ', '')}.pdf",
    mime="application/pdf"
)

# Botón para reiniciar pedido
st.markdown("---")
if st.button("🔁 Registrar otro pedido"):
    st.session_state.productos = []
    st.session_state.pedido_guardado = False
    st.rerun()

    
    st.session_state.productos = []
    
# === Historial por Cliente y Edición de Pedido ===
st.subheader("📋 Historial de Pedidos por Cliente")

nombre_cliente_filtro = st.text_input("Buscar cliente por nombre")
pedidos_filtrados = pedidos_df[pedidos_df["Nombre Cliente"].str.contains(nombre_cliente_filtro, case=False, na=False)]

if not pedidos_filtrados.empty:
    st.dataframe(pedidos_filtrados, use_container_width=True)

    pedido_ids = pedidos_filtrados["# Pedido"].unique().tolist()
    pedido_id_sel = st.selectbox("Selecciona un pedido para editar", pedido_ids)

    pedido_seleccionado = pedidos_df[pedidos_df["# Pedido"] == pedido_id_sel]

    if not pedido_seleccionado.empty:
        with st.expander(f"Editar Pedido #{pedido_id_sel}"):
            nuevo_estatus = st.selectbox("Nuevo Estatus", ["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"], 
                                         index=["Cotizacion", "Pendiente", "Pagado", "En Proceso", "Entregado"].index(pedido_seleccionado["Estatus"].iloc[0]))

            nuevo_producto = st.selectbox("Agregar Producto", productos_df["Producto"].unique())
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

                st.success("Producto agregado y pedido actualizado.")

            if st.button("Actualizar Estatus del Pedido"):
                pedidos_df.loc[pedidos_df["# Pedido"] == pedido_id_sel, "Estatus"] = nuevo_estatus
                guardar_pedidos(pedidos_df)
                st.success("Estatus actualizado.")
else:
    st.info("No se encontraron pedidos con ese nombre.")

# === Historial por Cliente con Edición y PDF ===
st.subheader("📋 Historial de Pedidos por Cliente")

nombre_cliente_filtro = st.text_input("Buscar cliente por nombre")
pedidos_filtrados = pedidos_df[pedidos_df["Nombre Cliente"].str.contains(nombre_cliente_filtro, case=False, na=False)]

if not pedidos_filtrados.empty:
    st.dataframe(pedidos_filtrados, use_container_width=True)

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

            nuevo_producto = st.selectbox("Agregar Producto", productos_df["Producto"].unique())
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

                st.success("✅ Producto agregado y pedido actualizado.")

            if st.button("Actualizar Estatus del Pedido"):
                pedidos_df.loc[pedidos_df["# Pedido"] == pedido_id_sel, "Estatus"] = nuevo_estatus
                guardar_pedidos(pedidos_df)
                st.success("✅ Estatus actualizado.")

            st.markdown("---")
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
else:
    st.info("🔍 No se encontraron pedidos con ese nombre.")

