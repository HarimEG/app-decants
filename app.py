# app.py — H DECANTS (v6: descarga directa de PDF sin abrir pestaña)
# =================================================================
import os
import base64
from datetime import datetime
from typing import List, Tuple

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from fpdf import FPDF
from dateutil.relativedelta import relativedelta

# =====================
# CONFIG Y CONSTANTES
# =====================
st.set_page_config(page_title="H DECANTS — Gestión de Pedidos", layout="wide")

LOGO_URL = "https://raw.githubusercontent.com/HarimEG/app-decants/main/hdecants_logo.jpg"
LOGO_LOCAL = "hdecants_logo.jpg"

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
        df["Stock disponible"] = pd.to_numeric(df["Stock disponible"], errors="coerce").fillna(0.0)
    return df

@st.cache_data(ttl=60, show_spinner=False)
def load_pedidos_df() -> pd.DataFrame:
    df = pd.DataFrame(pedidos_ws.get_all_records())
    if df.empty:
        return pd.DataFrame(columns=["# Pedido","Nombre Cliente","Fecha","Producto","Mililitros","Costo x ml","Total","Estatus"])
    for col in ["# Pedido", "Mililitros"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
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

def _get_product_row_idx(df: pd.DataFrame, nombre: str):
    try:
        idxs = df.index[df["Producto"] == nombre]
        return None if len(idxs) == 0 else idxs[0]
    except Exception:
        return None

def _get_stock(df: pd.DataFrame, idx) -> float:
    try:
        val = pd.to_numeric(df.at[idx, "Stock disponible"], errors="coerce")
        return float(0.0 if pd.isna(val) else val)
    except Exception:
        return 0.0

def _set_stock(df: pd.DataFrame, idx, nuevo: float):
    df.at[idx, "Stock disponible"] = max(0.0, round(float(nuevo), 3))

def ensure_session_keys():
    st.session_state.setdefault("pedido_items", [])   # [(prod, ml, costo, total)]
    st.session_state.setdefault("nueva_sesion", False)
    st.session_state.setdefault("ultimo_pdf_b64", None)
    st.session_state.setdefault("ultimo_pdf_nombre", None)

ensure_session_keys()

def link_descarga_pdf(pdf_bytes: bytes, filename: str) -> str:
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    return f'<a href="data:application/pdf;base64,{b64}" download="{filename}">⬇️ Descargar PDF</a>'

# =====================
# PDF
# =====================
def _try_load_unicode_font(pdf: FPDF) -> bool:
    """
    Usa DejaVuSans.ttf si está junto a app.py para emojis/acentos.
    Si no existe, usa Arial (sin emojis).
    """
    try:
        font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
        if os.path.exists(font_path):
            pdf.add_font("DejaVu", "", font_path, uni=True)
            pdf.add_font("DejaVu", "B", font_path, uni=True)
            pdf.set_font("DejaVu", "", 12)
            return True
    except Exception:
        pass
    pdf.set_font("Arial", "", 12)
    return False

def generar_pdf(pedido_id: int, cliente: str, fecha: str, estatus: str,
                productos: List[Tuple[str, float, float, float]]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Logo local si existe (no bloquea)
    try:
        if os.path.exists(LOGO_LOCAL):
            pdf.image(LOGO_LOCAL, x=160, y=8, w=30)
    except Exception:
        pass

    unicode_ok = _try_load_unicode_font(pdf)

    # Encabezado
    pdf.set_font("DejaVu" if unicode_ok else "Arial", "B", 15)
    pdf.cell(0, 10, f"Pedido #{pedido_id}", ln=True)

    pdf.set_font("DejaVu" if unicode_ok else "Arial", "", 12)
    pdf.cell(0, 8, f"{'👤 ' if unicode_ok else ''}Cliente: {cliente}", ln=True)
    pdf.cell(0, 8, f"{'📅 ' if unicode_ok else ''}Fecha: {fecha}", ln=True)
    pdf.cell(0, 8, f"{'📌 ' if unicode_ok else ''}Estatus: {estatus}", ln=True)
    pdf.ln(4)

    # Tabla
    pdf.set_font("DejaVu" if unicode_ok else "Arial", "B", 12)
    pdf.cell(90, 9, "Producto", 1)
    pdf.cell(25, 9, "ML", 1, 0, "C")
    pdf.cell(35, 9, "Costo/ml", 1, 0, "C")
    pdf.cell(35, 9, "Total", 1, 1, "C")

    total_general = 0.0
    pdf.set_font("DejaVu" if unicode_ok else "Arial", "", 11)
    for nombre, ml, costo, total in productos:
        total_general += float(total or 0.0)
        pdf.cell(90, 8, str(nombre)[:60], 1)
        pdf.cell(25, 8, f"{ml:g}", 1, 0, "C")
        pdf.cell(35, 8, f"${costo:,.2f}", 1, 0, "R")
        pdf.cell(35, 8, f"${float(total):,.2f}", 1, 1, "R")

    pdf.set_font("DejaVu" if unicode_ok else "Arial", "B", 12)
    pdf.cell(150, 9, "TOTAL GENERAL", 1, 0, "R")
    pdf.cell(35, 9, f"${total_general:,.2f}", 1, 1, "R")
    pdf.ln(6)

    # Leyenda de pago
    pdf.set_draw_color(210, 210, 210)
    x1, y1 = 10, pdf.get_y()
    pdf.line(x1, y1, 200, y1)
    pdf.ln(6)
    pdf.set_font("DejaVu" if unicode_ok else "Arial", "", 11)

    if unicode_ok:
        leyenda = (
            "💳 Una vez correcta la cotización, realiza el pago a la cuenta:\n\n"
            "🔢 4815 1632 0357 9563\n"
            "🏦 BBVA\n"
            "👤 Harim Escalona\n\n"
            "✅ Una vez confirmado el pago, se realiza el pedido."
        )
    else:
        leyenda = (
            "Una vez correcta la cotizacion, realiza el pago a la cuenta:\n\n"
            "4815 1632 0357 9563\n"
            "BBVA\n"
            "Harim Escalona\n\n"
            "Una vez confirmado el pago, se realiza el pedido."
        )
    pdf.multi_cell(0, 6, leyenda)

    try:
        return pdf.output(dest="S").encode("latin1")
    except Exception:
        return pdf.output(dest="S").encode("latin1", "ignore")

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
    # Reset de carrito si venimos de guardar y limpiar
    if st.session_state.get("nueva_sesion", False):
        st.session_state.pedido_items = []
        st.session_state.nueva_sesion = False
        st.session_state.ultimo_pdf_b64 = None
        st.session_state.ultimo_pdf_nombre = None

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
    # filtra opciones
            if not productos_df.empty:
                base_opts = productos_df["Producto"].astype(str)
                opciones = base_opts[base_opts.str.contains(search, case=False, na=False)] if search else base_opts
                opts_list = opciones.tolist()
            else:
                opts_list = []

    # multiselect como select de un solo elemento
            prod_pick = st.multiselect(
                "Producto",
                options=opts_list,
                default=opts_list[:1],     # si hay, precarga el primero
                key="picker_producto"
            )
                prod_sel = prod_pick[0] if prod_pick else "—"

        with c2:
            ml = st.number_input("ML", min_value=0.0, step=0.5, value=0.0)

        with c3:
            if not productos_df.empty and prod_sel in productos_df["Producto"].values:
                costo_actual = float(productos_df.loc[productos_df["Producto"]==prod_sel, "Costo x ml"].iloc[0])
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
                if not productos_df.empty and prod_sel in productos_df["Producto"].values:
                    idx = _get_product_row_idx(productos_df, prod_sel)
                    stock_disp = _get_stock(productos_df, idx) if idx is not None else 0.0
                else:
                    stock_disp = 0.0
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

        # Envío
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
        cart_items = list(st.session_state.pedido_items)  # Copia antes de tocar estado

        if not cliente or not cliente.strip():
            st.error("Ingrese el nombre del cliente.")
        elif not cart_items:
            st.error("El carrito está vacío. Agregue al menos un producto.")
        else:
            # Guardar filas en 'Pedidos' y ajustar stock
            nuevas_filas = []
            for prod, ml_val, costo_val, total_val in cart_items:
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
                # Ajuste de stock seguro
                if not productos_df.empty:
                    idx = _get_product_row_idx(productos_df, prod)
                    if idx is not None:
                        stock_disp = _get_stock(productos_df, idx)
                        _set_stock(productos_df, idx, stock_disp - float(ml_val))
                    else:
                        st.warning(f"⚠️ El producto '{prod}' no existe en 'Productos'. No se ajustó stock.")

            pedidos_df_new = pd.concat([pedidos_df, pd.DataFrame(nuevas_filas)], ignore_index=True)
            save_pedidos_df(pedidos_df_new)
            save_productos_df(productos_df)

            # Guardar envío
            if requiere_envio and datos_envio:
                datos_envio[0] = pedido_id
                datos_envio[1] = cliente.strip()
                append_envio_row(datos_envio)

            st.success(f"Pedido #{pedido_id} guardado.")

            # ========== FORZAR DESCARGA SIN ABRIR ==========
            pdf_bytes = generar_pdf(pedido_id, cliente.strip(), fecha.strftime("%Y-%m-%d"), estatus, cart_items)
            filename = f"Pedido_{pedido_id}_{cliente.replace(' ','')}.pdf"
            st.session_state.ultimo_pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            st.session_state.ultimo_pdf_nombre = filename
            st.markdown(
                f'<div style="padding:8px 0">{link_descarga_pdf(pdf_bytes, filename)}</div>',
                unsafe_allow_html=True
            )
            st.info("Puedes descargar el PDF arriba. Cuando termines, presiona el botón de abajo para limpiar y tomar otro pedido.")

    # Botón para limpiar y preparar nueva sesión (esto sí hace rerun)
    if st.session_state.get("ultimo_pdf_b64"):
        if st.button("🧹 Finalizar y limpiar"):
            st.session_state.pedido_items = []
            st.session_state.nueva_sesion = True
            st.session_state.ultimo_pdf_b64 = None
            st.session_state.ultimo_pdf_nombre = None
            st.rerun()

# =====================
# TAB 2: HISTORIAL (editor + PDF + duplicar)
# =====================
with tab2:
    st.subheader("📋 Historial y Edición de Pedidos")

    colf1, colf2, colf3 = st.columns([2,1,1])
    with colf1:
        filtro_cli = st.text_input("🔍 Cliente (contiene)", placeholder="Ej. Ana")
    with colf2:
        desde = st.date_input("Desde", value=datetime.today().date() - relativedelta(months=6))
    with colf3:
        hasta = st.date_input("Hasta", value=datetime.today().date())

    df_hist = pedidos_df.copy()
    if not df_hist.empty:
        if filtro_cli:
            df_hist = df_hist[df_hist["Nombre Cliente"].str.contains(filtro_cli, case=False, na=False)]
        if "Fecha" in df_hist.columns:
            df_hist["Fecha_dt"] = pd.to_datetime(df_hist["Fecha"], errors="coerce")
            df_hist = df_hist[(df_hist["Fecha_dt"] >= pd.to_datetime(desde)) & (df_hist["Fecha_dt"] <= pd.to_datetime(hasta))]
            df_hist = df_hist.drop(columns=["Fecha_dt"], errors="ignore")

    if df_hist.empty:
        st.info("No hay pedidos para el rango/cliente seleccionados.")
    else:
        st.dataframe(df_hist.sort_values(["# Pedido","Fecha"]), use_container_width=True, height=420)

        pedidos_ids = sorted(df_hist["# Pedido"].dropna().unique().tolist())
        pedido_sel = st.selectbox("🧾 Selecciona un pedido para editar / PDF", pedidos_ids)

        pedido_rows = pedidos_df[pedidos_df["# Pedido"] == pedido_sel].copy()
        if not pedido_rows.empty:
            cliente_sel = pedido_rows["Nombre Cliente"].iloc[0]
            estatus_actual = pedido_rows["Estatus"].iloc[-1]
            st.markdown(f"### Pedido #{pedido_sel} — {cliente_sel}")
            st.write(f"Estatus actual: **{estatus_actual}**")

            # Editor (ML editable)
            editable = pedido_rows[["Producto","Mililitros","Costo x ml","Total"]].copy()
            editable["Mililitros"] = pd.to_numeric(editable["Mililitros"], errors="coerce").fillna(0.0)
            editable["Costo x ml"] = pd.to_numeric(editable["Costo x ml"], errors="coerce").fillna(0.0)
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
                apply_changes = st.button("💾 Guardar cambios", key=f"save_{pedido_sel}")
            with colb3:
                gen_pdf = st.button("📄 Generar PDF", key=f"pdf_{pedido_sel}")
            with colb4:
                dup = st.button("🧬 Duplicar pedido", key=f"dup_{pedido_sel}")

            if apply_changes:
                cambios = edited.merge(pedido_rows[["Producto","Mililitros"]], on="Producto", how="left", suffixes=("_new","_old"))
                modificaciones = []
                for _, r in cambios.iterrows():
                    ml_old = float(r["Mililitros_old"])
                    ml_new = float(r["Mililitros_new"])
                    if ml_new != ml_old:
                        diff = ml_new - ml_old
                        idxp = _get_product_row_idx(productos_df, r["Producto"])
                        if idxp is None:
                            st.warning(f"⚠️ '{r['Producto']}' no existe en 'Productos'. No se ajustó stock.")
                        else:
                            stock_disp = _get_stock(productos_df, idxp)
                            if diff > 0 and diff > stock_disp:
                                st.error(f"Stock insuficiente para '{r['Producto']}'. Disponible: {stock_disp:g} ml")
                                st.stop()
                            _set_stock(productos_df, idxp, stock_disp - diff)
                        modificaciones.append((r["Producto"], ml_new))

                # Aplicar modificaciones a pedidos_df
                for prod, ml_new in modificaciones:
                    mask = (pedidos_df["# Pedido"] == pedido_sel) & (pedidos_df["Producto"] == prod)
                    pedidos_df.loc[mask, "Mililitros"] = ml_new
                    costo = float(pedidos_df.loc[mask, "Costo x ml"].iloc[0])
                    pedidos_df.loc[mask, "Total"] = float(ml_new) * costo

                # Estatus
                pedidos_df.loc[pedidos_df["# Pedido"] == pedido_sel, "Estatus"] = nuevo_estatus

                save_pedidos_df(pedidos_df)
                save_productos_df(productos_df)
                st.success("Cambios guardados.")
                st.rerun()

            if gen_pdf:
                productos_pdf = pedidos_df[pedidos_df["# Pedido"] == pedido_sel][["Producto","Mililitros","Costo x ml","Total"]].values.tolist()
                fecha_pdf = pedidos_df[pedidos_df["# Pedido"] == pedido_sel]["Fecha"].iloc[0]
                estatus_pdf = pedidos_df[pedidos_df["# Pedido"] == pedido_sel]["Estatus"].iloc[-1]
                pdf_bytes = generar_pdf(pedido_sel, cliente_sel, fecha_pdf, estatus_pdf, productos_pdf)
                filename_hist = f"Pedido_{pedido_sel}_{cliente_sel.replace(' ','')}.pdf"
                st.markdown(link_descarga_pdf(pdf_bytes, filename_hist), unsafe_allow_html=True)

            if dup:
                base = pedidos_df[pedidos_df["# Pedido"] == pedido_sel].copy()
                new_id = int(pd.to_numeric(pedidos_df["# Pedido"], errors="coerce").fillna(0).max()) + 1
                base["# Pedido"] = new_id
                base["Fecha"] = datetime.today().strftime("%Y-%m-%d")
                base["Estatus"] = "Cotizacion"
                pedidos_df2 = pd.concat([pedidos_df, base], ignore_index=True)
                save_pedidos_df(pedidos_df2)
                st.success(f"Pedido #{new_id} duplicado.")
                st.rerun()

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
            if not nombre_producto or not nombre_producto.strip() or costo_ml <= 0:
                st.error("Complete nombre y costo (>0).")
            else:
                if not productos_df.empty and nombre_producto.strip() in productos_df["Producto"].values:
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
                    st.rerun()

    st.markdown("### 🗂️ Lista de productos")
    if productos_df.empty:
        st.info("Aún no hay productos en la hoja **Productos**. Agrega el primero arriba.")
    else:
        editable_prod = productos_df.copy()
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
                st.rerun()

# =====================
# FOOTER
# =====================
st.caption("v6 — Descarga de PDF forzada (sin abrir), historial editable y stock robusto.")