@st.cache_data(ttl=30, show_spinner=False)
def load_compras_df() -> pd.DataFrame:
    # Asegura encabezados
    try:
        hdr = compras_ws.row_values(1)
    except Exception:
        hdr = []
    EXPECT = ["Producto","Pzs","Costo","Status","Mes","Fecha","Año",
              "De quien","Status de Pago","Decants","Vendedor"]
    if not hdr:
        compras_ws.update("A1", [EXPECT])
        return pd.DataFrame(columns=EXPECT)

    # Lee datos crudos (evita IndexError de get_all_records)
    try:
        # Trae un rango grande, filtra vacíos
        raw = compras_ws.get_values("A1:K10000")  # ajusta si necesitas más
    except Exception:
        raw = []

    if not raw:
        return pd.DataFrame(columns=EXPECT)

    # Normaliza filas: quita totalmente vacías y asegura ancho 11
    rows = []
    for r in raw[1:]:
        if not any(str(c).strip() for c in r):
            continue