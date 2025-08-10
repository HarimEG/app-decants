# app.py — H DECANTS (optimizado)
# =================================
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from dateutil.relativedelta import relativedelta
import base64
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont
import io
import requests

# Compatibilidad rerun (versiones nuevas/antiguas)
RERUN = getattr(st, "rerun", getattr(st, "experimental_rerun", None))

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

def link_pdf(bytes_pdf: bytes, filename: str) -> str:
    b64 = base64.b64encode(bytes_pdf).decode("utf-8")
    return f'<a href="data:application/pdf;base64,{b64}" target="_blank">📄 Ver PDF</a>', b64

# =====================
# IMAGEN DEL PEDIDO (PNG) — vertical, logo acotado y nítido
# =====================
def _cargar_logo_fit(url_o_path, max_w, max_h):
    """Carga logo y lo ajusta para no superar max_w x max_h (manteniendo proporción)."""
    try:
        if isinstance(url_o_path, str) and url_o_path.startswith("http"):
            r = requests.get(url_o_path, timeout=5)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
        else:
            img = Image.open(url_o_path).convert("RGBA")
        w, h = img.size
        ratio = min(max_w / float(w), max_h / float(h), 1.0)
        if ratio < 1.0:
            img = img.resize((int(w * ratio), int(h * ratio)))
        return img
    except Exception:
        return None

def _fit_text(draw, text, font, max_width):
    if not text:
        return ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ell = "…"
    t = text
    while t and draw.textlength(t + ell, font=font) > max_width:
        t = t[:-1]
    return (t + ell) if t else ell

def generar_imagen_pedido(pedido_id, cliente, fecha, estatus, productos, logo_url=None, portrait=False):
    """
    Genera un PNG horizontal, legible y nítido para compartir.
    - Ancho grande (1500 px base) y escala 2x para buena nitidez.
    - Fuentes más grandes para encabezado y tabla.
    - Logo limitado por ancho y alto del header (no invade la tabla).
    - Usa helpers: _cargar_logo_fit y _fit_text.
    """
    # ===== Tunables =====
    SCALE = 2               # 2 = nítido; 3 = súper nítido (archivo más pesado)
    ancho_base = 1500       # ancho final ~1500 px (sube/baja a gusto)
    h_header_base = 220     # alto del encabezado
    h_row_base = 56         # alto de cada fila de tabla
    h_footer_base = 130     # alto del pie de página
    # ====================

    margen = int(28 * SCALE)
    ancho   = int(ancho_base  * SCALE)
    h_header= int(h_header_base * SCALE)
    h_row   = int(h_row_base * SCALE)
    h_footer= int(h_footer_base * SCALE)

    filas = max(1, len(productos))
    alto = h_header + (filas + 2) * h_row + h_footer

    img = Image.new("RGB", (ancho, alto), "white")
    draw = ImageDraw.Draw(img)

    # Fuentes más grandes
    try:
        font_title = ImageFont.truetype("arial.ttf", int(42 * SCALE))
        font_sub   = ImageFont.truetype("arial.ttf", int(26 * SCALE))
        font_head  = ImageFont.truetype("arial.ttf", int(26 * SCALE))
        font_cell  = ImageFont.truetype("arial.ttf", int(24 * SCALE))
        font_bold  = ImageFont.truetype("arial.ttf", int(28 * SCALE))
    except Exception:
        font_title = font_sub = font_head = font_cell = font_bold = ImageFont.load_default()

    # ===== Encabezado (horizontal) =====
    draw.rectangle([0, 0, ancho, h_header], fill="#F4F6F8")

    # Área izquierda: textos
    col_left_x = margen
    col_left_w = int(ancho * 0.62)  # 62% para texto
    y = margen
    draw.text((col_left_x, y), f"Pedido #{int(pedido_id)}", font=font_title, fill="#131722")
    y += int(56 * SCALE)
    draw.text((col_left_x, y), f"Cliente: {cliente}", font=font_sub, fill="#333");   y += int(32 * SCALE)
    draw.text((col_left_x, y), f"Fecha: {fecha}",    font=font_sub, fill="#333");   y += int(32 * SCALE)
    draw.text((col_left_x, y), f"Estatus: {estatus}",font=font_sub, fill="#333")

    # Área derecha: logo (limitado)
    if logo_url is None:
        logo_url = globals().get("LOGO_URL", None)
    max_logo_w = int(ancho * 0.22)          # máx 22% del ancho total
    max_logo_h = int(h_header * 0.80)       # máx 80% del header
    logo = _cargar_logo_fit("hdecants_logo.jpg", max_logo_w, max_logo_h)
    if logo is None and logo_url:
        logo = _cargar_logo_fit(logo_url, max_logo_w, max_logo_h)
    if logo is not None:
        lw, lh = logo.size
        pos_x = ancho - margen - lw
        pos_y = (h_header - lh) // 2
        img.paste(logo, (pos_x, pos_y), logo)

    # Línea separadora
    draw.line([(margen, h_header), (ancho - margen, h_header)], fill="#DDE2E7", width=2)

    # ===== Tabla =====
    y = h_header + int(14 * SCALE)
    x = margen
    ancho_util = (ancho - 2 * margen)
    # Reparto de columnas más ancho
    w_prod  = int(ancho_util * 0.56)
    w_ml    = int(ancho_util * 0.10)
    w_costo = int(ancho_util * 0.16)
    w_total = int(ancho_util * 0.18)

    # Header de la tabla
    draw.rectangle([x, y, x + ancho_util, y + h_row], fill="#FAFBFC", outline="#DDE2E7")
    def row(cols):
        nonlocal y
        draw.line([(x, y), (x + ancho_util, y)], fill="#EEF1F4", width=1)
        cy = y + (h_row - int(26 * SCALE)) // 2
        cx = x
        for w, text, font, align in cols:
            pad = int(18 * SCALE)
            t = _fit_text(draw, str(text), font, w - 2 * pad)
            if align == "right":
                tx = cx + w - draw.textlength(t, font=font) - pad
            elif align == "center":
                tx = cx + (w - draw.textlength(t, font=font)) / 2
            else:
                tx = cx + pad
            draw.text((tx, cy), t, font=font, fill="#111")
            cx += w
        y += h_row

    row([(w_prod,"Producto",font_head,"left"),
         (w_ml,"ML",font_head,"center"),
         (w_costo,"Costo/ml",font_head,"right"),
         (w_total,"Total",font_head,"right")])

    # Filas (zebra)
    total_general = 0.0
    for i, fila in enumerate(productos or []):
        try:
            nombre, ml, costo, total = fila
        except Exception:
            continue
        total_general += float(total or 0.0)
        fill = "#FFFFFF" if i % 2 == 0 else "#FBFCFD"
        draw.rectangle([x, y, x + ancho_util, y + h_row], fill=fill)
        row([(w_prod,  nombre,            font_cell, "left"),
             (w_ml,    f"{ml:g}",          font_cell, "center"),
             (w_costo, f"${costo:,.2f}",   font_cell, "right"),
             (w_total, f"${total:,.2f}",   font_cell, "right")])

    # Total
    draw.line([(x, y + int(10 * SCALE)), (x + ancho_util, y + int(10 * SCALE))], fill="#DADFE4", width=1)
    y += int(20 * SCALE)
    row([(w_prod + w_ml + w_costo, "TOTAL:", font_bold, "right"),
         (w_total, f"${total_general:,.2f}", font_bold, "right")])

    # Pie
    y += int(24 * SCALE)
    draw.text((margen, y), "Gracias por su compra — H DECANTS", font=font_sub, fill="#67717E")

    # Exportar: downscale para nitidez
    final = img.resize((ancho // SCALE, alto // SCALE), Image.LANCZOS)
    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

# =====================
# ESTADO INICIAL
# =====================
def ensure_session_keys():
    st.session_state.setdefault("pedido_items", [])
    st.session_state.setdefault("nueva_sesion", False)

ensure_session_keys()
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
            img_bytes = generar_imagen_pedido(
                pedido_id, cliente.strip(), fecha.strftime("%Y-%m-%d"),
                estatus, st.session_state.pedido_items,
                logo_url=LOGO_URL
            )
            st.image(img_bytes, caption=f"Pedido #{pedido_id}", use_column_width=True)
            st.download_button(
                "⬇️ Descargar Imagen", img_bytes,
                file_name=f"Pedido_{pedido_id}_{cliente.replace(' ','')}.png",
                mime="image/png"
            )

            st.session_state.pedido_items = []
            st.session_state.nueva_sesion = True
            if RERUN:
                RERUN()

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

    df_hist = pedidos_df.copy()
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

        pedido_rows = pedidos_df[pedidos_df["# Pedido"] == pedido_sel].copy()
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
                nuevo_estatus = st.selectbox("Cambiar estatus", ESTATUS_LIST, index=ESTATUS_LIST.index(estatus_actual) if estatus_actual in ESTATUS_LIST else 0)
            with colb2:
                apply_changes = st.button("💾 Guardar cambios")
            with colb3:
                gen_img = st.button("🖼️ Generar Imagen")
            with colb4:
                dup = st.button("🧬 Duplicar pedido")

            if apply_changes:
                cambios = edited.merge(pedido_rows[["Producto","Mililitros"]], on="Producto", how="left", suffixes=("_new","_old"))
                modificaciones = []
                for _, r in cambios.iterrows():
                    ml_old = float(r["Mililitros_old"])
                    ml_new = float(r["Mililitros_new"])
                    if ml_new != ml_old:
                        diff = ml_new - ml_old
                        idxp = productos_df.index[productos_df["Producto"]==r["Producto"]][0]
                        stock_disp = float(productos_df.at[idxp, "Stock disponible"])
                        if diff > 0 and diff > stock_disp:
                            st.error(f"Stock insuficiente para '{r['Producto']}'. Disponible: {stock_disp:g} ml")
                            st.stop()
                        productos_df.at[idxp, "Stock disponible"] = stock_disp - diff
                        modificaciones.append((r["Producto"], ml_new))

                for prod, ml_new in modificaciones:
                    mask = (pedidos_df["# Pedido"] == pedido_sel) & (pedidos_df["Producto"] == prod)
                    pedidos_df.loc[mask, "Mililitros"] = ml_new
                    costo = float(pedidos_df.loc[mask, "Costo x ml"].iloc[0])
                    pedidos_df.loc[mask, "Total"] = float(ml_new) * costo

                pedidos_df.loc[pedidos_df["# Pedido"] == pedido_sel, "Estatus"] = nuevo_estatus

                save_pedidos_df(pedidos_df)
                save_productos_df(productos_df)
                st.success("Cambios guardados.")
                if RERUN:
                    RERUN()

            if gen_img:
                productos_img = pedidos_df[pedidos_df["# Pedido"] == pedido_sel][["Producto","Mililitros","Costo x ml","Total"]].values.tolist()
                fecha_img = pedidos_df[pedidos_df["# Pedido"] == pedido_sel]["Fecha"].iloc[0]
                estatus_img = pedidos_df[pedidos_df["# Pedido"] == pedido_sel]["Estatus"].iloc[-1]
                img_bytes = generar_imagen_pedido(
                    pedido_sel, cliente_sel, fecha_img, estatus_img, productos_img,
                    logo_url=LOGO_URL
                )
                st.image(img_bytes, caption=f"Pedido #{pedido_sel}", use_column_width=True)
                st.download_button("📥 Descargar Imagen", img_bytes,
                                   file_name=f"Pedido_{pedido_sel}_{cliente_sel.replace(' ','')}.png",
                                   mime="image/png")

            if dup:
                base = pedidos_df[pedidos_df["# Pedido"] == pedido_sel].copy()
                new_id = next_pedido_id(pedidos_df)
                base["# Pedido"] = new_id
                base["Fecha"] = datetime.today().strftime("%Y-%m-%d")
                base["Estatus"] = "Cotizacion"
                pedidos_df2 = pd.concat([pedidos_df, base], ignore_index=True)
                save_pedidos_df(pedidos_df2)
                st.success(f"Pedido #{new_id} duplicado.")
                if RERUN:
                    RERUN()

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
                    if RERUN:
                        RERUN()

    st.markdown("### 🗂️ Lista de productos")
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
            if RERUN:
                RERUN()

# =====================
# FOOTER
# =====================
st.caption("v2 — Optimizado para flujo rápido de pedidos, edición segura y CRUD de productos.")