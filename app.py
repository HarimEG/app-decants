# app.py — H DECANTS (v3)
# =======================
# - PDF con leyenda de pago
# - Selector de producto optimizado para móvil
# - Editor inline de pedidos con ajuste de stock
# - CRUD de productos
# - Evita rerun inmediato tras guardar (PDF permanece)
# - Compatible con Python 3.9

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import List, Tuple
import base64

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
    """
    Genera un PDF con el detalle del pedido y una leyenda de pago al final.
    """
    pdf = FPDF()
    pdf.add_page()

    # Logo (si existe local, si no, ignoramos)
    try:
        pdf.image("hdecants_logo.jpg", x=160, y=10, w=35)
    except Exception:
        pass

    pdf.set_auto_page_break(auto=True, margin=15)

    # Encabezado
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Pedido #{pedido_id}", ln=True)

    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Cliente: {cliente}", ln=True)
    pdf.cell(0, 8, f"Fecha: {fecha}", ln=True)
    pdf.cell(0, 8, f"Estatus: {estatus}", ln=True)
    pdf.ln(6)

    # Tabla
    pdf.set_font("Arial", "B", 12)
    pdf.cell(95, 9, "Producto", 1)
    pdf.cell(20, 9, "ML", 1, 0, "C")
    pdf.cell(35, 9, "Costo/ml", 1, 0, "C")
    pdf.cell(35, 9, "Total", 1, 1, "C")

    total_general = 0.0
    pdf.set_font("Arial", "", 11)
    for nombre, ml, costo, total in productos:
        total_general += float(total or 0.0)
        nombre_str = str(nombre)[:60]
        pdf.cell(95, 8, nombre_str, 1)
        pdf.cell(20, 8, f"{ml:g}", 1, 0, "C")
        pdf.cell(35, 8, f"${costo:.2f}", 1, 0, "R")
        pdf.cell(35, 8, f"${total:.2f}", 1, 1, "R")

    pdf.set_font("Arial", "B", 12)
    pdf.cell(150, 9, "TOTAL", 1, 0, "R")
    pdf.cell(35, 9, f"${total_general:.2f}", 1, 1, "R")
    pdf.ln(6)

    # Leyenda de pago
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(
        0, 7,
        "💳 Forma de pago\n"
        "Banco: BBVA\n"
        "Titular: Harim Escalona\n"
        "Cuenta/Tarjeta: 4815 1632 0357 9563\n\n"
        "✅ Si la cotización es correcta, realiza el pago y comparte el comprobante.\n"
        "🚚 Una vez confirmado el pago, tu pedido se prepara y se envía."
    )

    return pdf.output(dest="S").encode("latin1")

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
        c1, c2, c3, c4 = st.columns([3,1.2,1.2,0.9])
        with c1:
            search = st.text_input("Buscar producto", placeholder="Escribe parte del nombre", key="buscador_prod")
            if not productos_df.empty:
                base_opts = productos_df["Producto"].astype(str)
                opciones = base_opts[base_opts.str.contains(search, case=False, na=False)] if search else base_opts
                opts_list = opciones.tolist()
            else:
                opts_list = []
            # multiselect para móvil (lo usamos como select de 1)
            prod_pick = st.multiselect("Producto", options=opts_list, default=opts_list[:1], key="picker_producto")
            prod_sel = prod_pick[0] if prod_pick else "—"

        with c2:
            ml = st.number_input("ML", min_value=0.0, step=0.5, value=0.0)
        with c3:
            if (not productos_df.empty) and (prod_sel in productos_df["Producto"].values):
                costo_actual = float(productos_df.loc[productos_df["Producto"] == prod_sel, "Costo x ml"].iloc[0])
            else:
                costo_actual = 0.0
            st.number_input("Costo/ml (ref)", value=float(costo_actual), disabled=True, key="costo_ref")
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
        else:
            st.info("El carrito está vacío. Agrega al menos un producto.")

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
                datos_envio = [None, None, nombre_dest, calle, colonia, cp, ciudad, estado, telefono, referencia]

        submitted = st.form_submit_button("💾 Guardar Pedido", type="primary")

    if submitted:
        if not cliente.strip():
            st.error("Ingrese el nombre del cliente.")
        elif not st.session_state.pedido_items:
            st.error("Agregue al menos un producto.")
        else:
            # Actualiza stock y agrega filas
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
                productos_df.at[idx, "Stock disponible"] = float(productos_df.at[idx, "Stock disponible"]) - float(ml_val)

            pedidos_df_new = pd.concat([pedidos_df, pd.DataFrame(nuevas_filas)], ignore_index=True)
            save_pedidos_df(pedidos_df_new)
            save_productos_df(productos_df)

            if requiere_envio and datos_envio:
                datos_envio[0] = pedido_id
                datos_envio[1] = cliente.strip()
                append_envio_row(datos_envio)

            st.success(f"Pedido #{pedido_id} guardado.")

            # Botón de descarga del PDF (no abre pestaña, descarga directo)
            pdf_bytes = generar_pdf(
                pedido_id, cliente.strip(), fecha.strftime("%Y-%m-%d"), estatus, st.session_state.pedido_items
            )
            st.download_button(
                "📥 Descargar PDF",
                pdf_bytes,
                file_name=f"Pedido_{pedido_id}_{cliente.replace(' ','')}.pdf",
                mime="application/pdf"
            )

            # Botón para iniciar nueva cotización
            if st.button("🆕 Nueva cotización"):
                st.session_state.pedido_items = []
                st.session_state.nueva_sesion = True
                st.experimental_rerun()

# =====================
# TAB 2: HISTORIAL
# =====================
with tab2:
    st.subheader("📋 Historial y Edición de Pedidos")
    colf1, colf2, colf3 = st.columns([2,1,1])
    with colf1:
        filtro_cli = st.text_input("🔍 Cliente (contiene)", placeholder="Ej. Ana")
    with colf2:
        desde = st.date_input("Desde", value=datetime.today().date() - relativedelta(months=1))
    with colf3:
        hasta = st.date_input("Hasta", value=datetime.today().date())

    df_hist = load_pedidos_df().copy()
    if filtro_cli:
        df_hist = df_hist[df_hist["Nombre Cliente"].str.contains(filtro_cli, case=False, na=False)]
    df_hist["Fecha_dt"] = pd.to_datetime(df_hist["Fecha"], errors="coerce")
    df_hist = df_hist[(df_hist["Fecha_dt"]>=pd.to_datetime(desde)) & (df_hist["Fecha_dt"]<=pd.to_datetime(hasta))]
    df_hist = df_hist.drop(columns=["Fecha_dt"])

    st.dataframe(
        df_hist.sort_values(["# Pedido","Fecha"]),
        use_container_width=True,
        height=420
    )

    if not df_hist.empty:
        pedidos_ids = sorted(df_hist["# Pedido"].dropna().unique().tolist())
        pedido_sel = st.selectbox("Selecciona un pedido", pedidos_ids)

        pedido_rows = load_pedidos_df()
        pedido_rows = pedido_rows[pedido_rows["# Pedido"] == pedido_sel].copy()
        if not pedido_rows.empty:
            cliente_sel = pedido_rows["Nombre Cliente"].iloc[0]
            estatus_actual = pedido_rows["Estatus"].iloc[-1]

            st.markdown(f"### Pedido #{pedido_sel} — {cliente_sel}")
            st.write(f"Estatus actual: **{estatus_actual}**")

            editable = pedido_rows[["Producto","Mililitros","Costo x ml","Total"]].copy()
            editable["Mililitros"] = editable["Mililitros"].astype(float)
            editable["Costo x ml"] = editable["Costo x ml"].astype(float)
            editable["Total"] = (editable["Mililitros"] * editable["Costo x ml"]).round(2)

            edited = st.data_editor(
                editable,
                use_container_width=True,
                num_rows="dynamic",
                disabled=["Costo x ml","Total"],
                key=f"editor_{pedido_sel}"
            )

            colb1, colb2, colb3, colb4 = st.columns(4)
            with colb1:
                nuevo_estatus = st.selectbox("Cambiar estatus", ESTATUS_LIST,
                                             index=ESTATUS_LIST.index(estatus_actual) if estatus_actual in ESTATUS_LIST else 0)
            with colb2:
                apply_changes = st.button("💾 Guardar cambios")
            with colb3:
                gen_pdf = st.button("📄 Generar PDF")
            with colb4:
                dup = st.button("🧬 Duplicar pedido")

            if apply_changes:
                prod_df = load_productos_df()
                cambios = edited.merge(pedido_rows[["Producto","Mililitros"]], on="Producto", how="left", suffixes=("_new","_old"))
                modificaciones = []
                for _, r in cambios.iterrows():
                    ml_old = float(r["Mililitros_old"]); ml_new = float(r["Mililitros_new"])
                    if ml_new != ml_old:
                        diff = ml_new - ml_old
                        idxp = prod_df.index[prod_df["Producto"]==r["Producto"]][0]
                        stock_disp = float(prod_df.at[idxp, "Stock disponible"])
                        if diff > 0 and diff > stock_disp:
                            st.error(f"Stock insuficiente para '{r['Producto']}'. Disponible: {stock_disp:g} ml")
                            st.stop()
                        prod_df.at[idxp, "Stock disponible"] = stock_disp - diff
                        modificaciones.append((r["Producto"], ml_new))

                pedidos_all = load_pedidos_df()
                for prod, ml_new in modificaciones:
                    mask = (pedidos_all["# Pedido"] == pedido_sel) & (pedidos_all["Producto"] == prod)
                    pedidos_all.loc[mask, "Mililitros"] = ml_new
                    costo = float(pedidos_all.loc[mask, "Costo x ml"].iloc[0])
                    pedidos_all.loc[mask, "Total"] = float(ml_new) * costo

                pedidos_all.loc[pedidos_all["# Pedido"] == pedido_sel, "Estatus"] = nuevo_estatus
                save_pedidos_df(pedidos_all)
                save_productos_df(prod_df)
                st.success("Cambios guardados.")
                st.experimental_rerun()

            if gen_pdf:
                pedidos_all = load_pedidos_df()
                productos_pdf = pedidos_all[pedidos_all["# Pedido"] == pedido_sel][["Producto","Mililitros","Costo x ml","Total"]].values.tolist()
                fecha_pdf = pedidos_all[pedidos_all["# Pedido"] == pedido_sel]["Fecha"].iloc[0]
                estatus_pdf = pedidos_all[pedidos_all["# Pedido"] == pedido_sel]["Estatus"].iloc[-1]
                pdf_bytes = generar_pdf(pedido_sel, cliente_sel, fecha_pdf, estatus_pdf, productos_pdf)
                st.download_button("📥 Descargar PDF", pdf_bytes,
                                   file_name=f"Pedido_{pedido_sel}_{cliente_sel.replace(' ','')}.pdf",
                                   mime="application/pdf")

            if dup:
                base = pedido_rows.copy()
                new_id = next_pedido_id(load_pedidos_df())
                base["# Pedido"] = new_id
                base["Fecha"] = datetime.today().strftime("%Y-%m-%d")
                base["Estatus"] = "Cotizacion"
                pedidos_df2 = pd.concat([load_pedidos_df(), base], ignore_index=True)
                save_pedidos_df(pedidos_df2)
                st.success(f"Pedido #{new_id} duplicado.")
                st.experimental_rerun()

# =====================
# TAB 3: PRODUCTOS
# =====================
with tab3:
    st.subheader("🧪 Gestión de Productos")
    st.markdown("Agregue nuevos perfumes o edite costo/stock existente.")

    with st.expander("➕ Agregar nuevo perfume", expanded=False):
        cpa, cpb, cpc = st.columns([2,1,1])
        with cpa:
            nombre_producto = st.text_input("Nombre del producto", key="np_nombre")
        with cpb:
            costo_ml = st.number_input("Costo por ml", min_value=0.0, step=0.1, key="np_costo")
        with cpc:
            stock_ini = st.number_input("Stock disponible (ml)", min_value=0.0, step=1.0, key="np_stock")
        if st.button("Agregar", key="np_add"):
            if not nombre_producto.strip() or costo_ml <= 0:
                st.error("Complete nombre y costo (>0).")
            else:
                productos_df = load_productos_df()
                if nombre_producto.strip() in productos_df["Producto"].values:
                    st.warning("Ese producto ya existe.")
                else:
                    nuevo = pd.DataFrame([{
                        "Producto": nombre_producto.strip(),
                        "Costo x ml": float(costo_ml),
                        "Stock disponible": float(stock_ini)
                    }])
                    productos_df2 = pd.concat([productos_df, nuevo], ignore_index=True)
                    save_productos_df(productos_df2)
                    st.success("Producto agregado.")
                    st.experimental_rerun()

    st.markdown("### 🗂️ Lista de productos")
    editable_prod = load_productos_df().copy()
    edited_prod = st.data_editor(
        editable_prod,
        use_container_width=True,
        num_rows="dynamic",
        key="prod_editor"
    )
    if st.button("💾 Guardar cambios de productos"):
        if edited_prod["Costo x ml"].lt(0).any() or edited_prod["Stock disponible"].lt(0).any():
            st.error("Costo y stock deben ser >= 0.")
        else:
            save_productos_df(edited_prod)
            st.success("Cambios guardados.")
            st.experimental_rerun()

# =====================
# FOOTER
# =====================
st.caption("v3 — Flujo de pedidos con PDF y leyenda de pago incluida.")