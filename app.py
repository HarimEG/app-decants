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
    PNG HORIZONTAL con texto grande y TOTAL destacado.
    - Ancho final ~1800 px (ideal para WhatsApp y lectura).
    - Fuentes grandes para filas, encabezados y total.
    - Logo acotado (no invade la tabla).
    Requiere helpers: _cargar_logo_fit y _fit_text.
    """
    # Tamaño / nitidez
    SCALE = 2                 # 2 = nítido; 3 = súper nítido (archivo más pesado)
    ancho_base = 1800         # más ancho => texto más grande al compartir
    h_header_base = 260       # header más alto
    h_row_base = 78           # filas altas
    h_footer_base = 160

    # Espaciado
    margen = int(34 * SCALE)
    ancho   = int(ancho_base  * SCALE)
    h_header= int(h_header_base * SCALE)
    h_row   = int(h_row_base * SCALE)
    h_footer= int(h_footer_base * SCALE)

    filas = max(1, len(productos))
    alto = h_header + (filas + 2) * h_row + h_footer

    img = Image.new("RGB", (ancho, alto), "white")
    draw = ImageDraw.Draw(img)

    # Fuentes GRANDES
    try:
        font_title = ImageFont.truetype("arial.ttf", int(56 * SCALE))
        font_sub   = ImageFont.truetype("arial.ttf", int(34 * SCALE))
        font_head  = ImageFont.truetype("arial.ttf", int(32 * SCALE))
        font_cell  = ImageFont.truetype("arial.ttf", int(30 * SCALE))
        font_bold  = ImageFont.truetype("arial.ttf", int(38 * SCALE))  # para TOTAL
    except Exception:
        font_title = font_sub = font_head = font_cell = font_bold = ImageFont.load_default()

    # ===== Encabezado =====
    draw.rectangle([0, 0, ancho, h_header], fill="#F4F6F8")

    # Textos izquierda
    y = margen
    draw.text((margen, y), f"Pedido #{int(pedido_id)}", font=font_title, fill="#131722")
    y += int(68 * SCALE)
    draw.text((margen, y), f"Cliente: {cliente}", font=font_sub, fill="#333");   y += int(38 * SCALE)
    draw.text((margen, y), f"Fecha:   {fecha}",   font=font_sub, fill="#333");   y += int(38 * SCALE)
    draw.text((margen, y), f"Estatus: {estatus}", font=font_sub, fill="#333")

    # Logo derecha (limitado)
    if logo_url is None:
        logo_url = globals().get("LOGO_URL", None)
    max_logo_w = int(ancho * 0.22)
    max_logo_h = int(h_header * 0.80)
    logo = _cargar_logo_fit("hdecants_logo.jpg", max_logo_w, max_logo_h)
    if logo is None and logo_url:
        logo = _cargar_logo_fit(logo_url, max_logo_w, max_logo_h)
    if logo is not None:
        lw, lh = logo.size
        img.paste(logo, (ancho - margen - lw, (h_header - lh) // 2), logo)

    draw.line([(margen, h_header), (ancho - margen, h_header)], fill="#DDE2E7", width=3)

    # ===== Tabla =====
    y = h_header + int(18 * SCALE)
    x = margen
    ancho_util = (ancho - 2 * margen)

    # Columnas: más espacio a Costo y Total para que se vean
    w_prod  = int(ancho_util * 0.50)
    w_ml    = int(ancho_util * 0.10)
    w_costo = int(ancho_util * 0.18)
    w_total = int(ancho_util * 0.22)

    def row_bg(y0, color):
        draw.rectangle([x, y0, x + ancho_util, y0 + h_row], fill=color)

    def row_text(cols, y0):
        cx = x
        pad_x = int(22 * SCALE)
        baseline = y0 + (h_row - int(30 * SCALE)) // 2
        for w, text, font, align, color in cols:
            t = _fit_text(draw, str(text), font, w - 2 * pad_x)
            if align == "right":
                tx = cx + w - draw.textlength(t, font=font) - pad_x
            elif align == "center":
                tx = cx + (w - draw.textlength(t, font=font)) / 2
            else:
                tx = cx + pad_x
            draw.text((tx, baseline), t, font=font, fill=color)
            cx += w

    # Header tabla
    row_bg(y, "#FAFBFC")
    row_text([
        (w_prod,  "Producto", font_head, "left",   "#111"),
        (w_ml,    "ML",       font_head, "center", "#111"),
        (w_costo, "Costo/ml", font_head, "right",  "#111"),
        (w_total, "Total",    font_head, "right",  "#111"),
    ], y)
    y += h_row

    # Filas
    total_general = 0.0
    for i, fila in enumerate(productos or []):
        try:
            nombre, ml, costo, total = fila
        except Exception:
            continue
        total_general += float(total or 0.0)
        row_bg(y, "#FFFFFF" if i % 2 == 0 else "#F7F9FC")
        row_text([
            (w_prod,  nombre,           font_cell, "left",   "#0F172A"),
            (w_ml,    f"{ml:g}",         font_cell, "center", "#0F172A"),
            (w_costo, f"${costo:,.2f}",  font_cell, "right",  "#0F172A"),
            (w_total, f"${total:,.2f}",  font_cell, "right",  "#0F172A"),
        ], y)
        y += h_row

    # TOTAL destacado
    y += int(10 * SCALE)
    draw.line([(x, y), (x + ancho_util, y)], fill="#DADFE4", width=2)
    y += int(14 * SCALE)
    row_bg(y, "#FFF6E5")  # banda suave
    row_text([
        (w_prod + w_ml + w_costo, "TOTAL", font_bold, "right", "#7A3E00"),
        (w_total, f"${total_general:,.2f}", font_bold, "right", "#7A3E00"),
    ], y)
    y += h_row

    # Pie
    y += int(24 * SCALE)
    draw.text((margen, y), "Gracias por su compra — H DECANTS", font=font_sub, fill="#667085")

    # Exportar nítido (downscale)
    final = img.resize((ancho // SCALE, alto // SCALE), Image.LANCZOS)
    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

# =====================
# FOOTER
# =====================
st.caption("v2 — Optimizado para flujo rápido de pedidos, edición segura y CRUD de productos.")