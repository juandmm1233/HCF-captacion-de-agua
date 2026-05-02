"""
Simulación dinámica de aprovechamiento de agua lluvia — Universidad Cooperativa de Colombia (UCC).

Motor basado en balance de masas (stocks y flujos): el tanque acumula entradas (captación)
y salidas (consumo), con límites físicos (rebalse) y cobertura de déficit con agua potable.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# --- Constantes de columnas esperadas ---
COL_FECHA = "Fecha"
COL_PRECIP = "Precipitacion_mm"


def generar_precipitacion_sintetica(
    dias: int = 365,
    fecha_inicio: datetime | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Genera una serie diaria sintética de precipitación (mm) con estacionalidad húmeda/seca.
    Permite usar la app sin archivo de entrada.
    """
    rng = np.random.default_rng(seed)
    if fecha_inicio is None:
        fecha_inicio = datetime(2025, 1, 1)
    fechas = [fecha_inicio + timedelta(days=i) for i in range(dias)]
    # Índice día del año 0..364 para patrón estacional (Colombia: mayor lluvia en mitad de año aprox.)
    doy = np.array([d.timetuple().tm_yday - 1 for d in fechas])
    estacional = 8.0 + 6.0 * np.sin(2 * np.pi * (doy - 80) / 365.0)
    ruido = rng.gamma(shape=1.2, scale=2.5, size=dias)
    precip = np.maximum(estacional + ruido - 3.0, 0.0)
    return pd.DataFrame({COL_FECHA: fechas, COL_PRECIP: precip})


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Mapea variantes de nombres de columnas a Fecha y Precipitacion_mm."""
    col_map = {c.lower().strip(): c for c in df.columns}
    ren: dict[str, str] = {}
    for key, canon in [
        ("fecha", COL_FECHA),
        ("date", COL_FECHA),
        ("precipitacion_mm", COL_PRECIP),
        ("precipitación_mm", COL_PRECIP),
        ("precipitacion", COL_PRECIP),
        ("precip", COL_PRECIP),
        ("p_mm", COL_PRECIP),
    ]:
        if key in col_map:
            ren[col_map[key]] = canon
    out = df.rename(columns=ren)
    if COL_FECHA not in out.columns or COL_PRECIP not in out.columns:
        raise ValueError(
            "El archivo debe incluir columnas de fecha y precipitación "
            f"(ej. '{COL_FECHA}', '{COL_PRECIP}')."
        )
    out = out[[COL_FECHA, COL_PRECIP]].copy()
    out[COL_FECHA] = pd.to_datetime(out[COL_FECHA], errors="coerce")
    out[COL_PRECIP] = pd.to_numeric(out[COL_PRECIP], errors="coerce")
    out = out.dropna(subset=[COL_FECHA, COL_PRECIP])
    out = out.sort_values(COL_FECHA).reset_index(drop=True)
    return out


def cargar_precipitaciones(uploaded) -> pd.DataFrame:
    """Lee CSV o Excel desde el objeto de subida de Streamlit."""
    name = (uploaded.name or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded)
    else:
        raise ValueError("Formato no soportado. Use CSV o Excel (.csv, .xlsx).")
    return normalizar_columnas(df)


def simular_aprovechamiento(
    precip_df: pd.DataFrame,
    area_captacion_m2: float,
    coef_escorrentia: float,
    eficiencia: float,
    capacidad_tanque_m3: float,
    consumo_diario_m3: float,
    stock_inicial_m3: float = 0.0,
) -> pd.DataFrame:
    """
    Simulación día a día (stocks y flujos):

    1) Captación (flujo de entrada, m³/día):
       Profundidad convertida a volumen: h(m) = Precip(mm)/1000.
       Volumen bruto = h * Área(m²). Se aplican coef. escorrentía y eficiencia del sistema.

    2) Tras la captación, el stock provisional puede superar la capacidad → rebalse (pérdida)
       y el stock se recorta al máximo físico.

    3) Consumo (flujo de salida): si el stock cubre el consumo, se usa solo agua de lluvia;
       si no, se completa con agua potable suplementaria y el stock queda en 0.
    """
    n = len(precip_df)
    fechas = precip_df[COL_FECHA].values
    precip_mm = precip_df[COL_PRECIP].astype(float).values

    stock = np.zeros(n)
    captacion = np.zeros(n)
    rebalse = np.zeros(n)
    agua_potable = np.zeros(n)
    consumo_arr = np.full(n, consumo_diario_m3)

    s = float(stock_inicial_m3)

    for i in range(n):
        # Captación: mm → m de lámina; * área (m²) → m³
        cap = (
            (precip_mm[i] / 1000.0)
            * area_captacion_m2
            * coef_escorrentia
            * eficiencia
        )
        captacion[i] = cap
        # Stock después de entrada
        s = s + cap
        if s > capacidad_tanque_m3:
            rebalse[i] = s - capacidad_tanque_m3
            s = capacidad_tanque_m3
        # Consumo y déficit
        dem = consumo_diario_m3
        if s >= dem:
            s = s - dem
            agua_potable[i] = 0.0
        else:
            agua_potable[i] = dem - s
            s = 0.0
        stock[i] = s

    return pd.DataFrame(
        {
            COL_FECHA: fechas,
            COL_PRECIP: precip_mm,
            "Captacion_m3": captacion,
            "Rebose_m3": rebalse,
            "Consumo_m3": consumo_arr,
            "Agua_Potable_Suple_m3": agua_potable,
            "Stock_Tanque_m3": stock,
        }
    )


def calcular_kpis(resultado: pd.DataFrame) -> dict[str, float]:
    """KPIs agregados a partir de la serie simulada."""
    total_demanda = float(resultado["Consumo_m3"].sum())
    total_potable = float(resultado["Agua_Potable_Suple_m3"].sum())
    # Agua “ahorrada” = volumen de demanda satisfecho con agua captada (no con red)
    total_ahorrado = total_demanda - total_potable
    eficiencia_pct = (100.0 * total_ahorrado / total_demanda) if total_demanda > 0 else 0.0
    return {
        "total_ahorrado_m3": total_ahorrado,
        "total_potable_m3": total_potable,
        "eficiencia_pct": eficiencia_pct,
        "total_demanda_m3": total_demanda,
    }


def grafico_nivel_tanque(resultado: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=resultado[COL_FECHA],
            y=resultado["Stock_Tanque_m3"],
            mode="lines",
            name="Nivel del tanque (m³)",
            line=dict(color="#1f77b4", width=2),
            fill="tozeroy",
            fillcolor="rgba(31, 119, 180, 0.15)",
        )
    )
    fig.update_layout(
        title="Evolución del nivel del tanque",
        xaxis_title="Fecha",
        yaxis_title="Volumen almacenado (m³)",
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def main() -> None:
    st.set_page_config(
        page_title="Aprovechamiento de agua lluvia — UCC",
        page_icon="💧",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.2rem; }
        div[data-testid="stMetric"] {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 12px 16px;
        }
        h1 { letter-spacing: -0.02em; }
        .ucc-sub { color: #64748b; font-size: 0.95rem; margin-top: -0.5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Simulación dinámica — Aprovechamiento de agua lluvia")
    st.markdown(
        '<p class="ucc-sub">Universidad Cooperativa de Colombia (UCC) · Panel de balance stocks–flujos</p>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Parámetros del sistema")
        area = st.slider("Área de captación (m²)", min_value=10.0, max_value=2000.0, value=120.0, step=5.0)
        coef_esc = st.slider("Coeficiente de escorrentía", min_value=0.0, max_value=1.0, value=0.85, step=0.01)
        eficiencia = st.slider("Eficiencia del sistema", min_value=0.0, max_value=1.0, value=0.90, step=0.01)
        capacidad = st.number_input(
            "Capacidad del tanque (m³)",
            min_value=1.0,
            max_value=500.0,
            value=25.0,
            step=0.5,
        )
        consumo = st.number_input(
            "Consumo diario equivalente (m³/día)",
            min_value=0.01,
            max_value=20.0,
            value=0.8,
            step=0.05,
            help="Demanda diaria atendida prioritariamente con agua captada.",
        )
        stock0 = st.number_input("Stock inicial del tanque (m³)", min_value=0.0, value=0.0, step=0.5)

        st.divider()
        st.subheader("Datos de precipitación")
        archivo = st.file_uploader(
            "Subir CSV o Excel",
            type=["csv", "xlsx", "xls"],
            help=f"Columnas requeridas: '{COL_FECHA}' y '{COL_PRECIP}' (o nombres equivalentes).",
        )

    # Datos: archivo o sintéticos
    try:
        if archivo is not None:
            precip_df = cargar_precipitaciones(archivo)
            st.session_state["origen_datos"] = f"Archivo: {archivo.name}"
        else:
            precip_df = generar_precipitacion_sintetica()
            st.session_state["origen_datos"] = "Serie sintética (1 año)"
    except Exception as e:
        st.error(str(e))
        precip_df = generar_precipitacion_sintetica()
        st.session_state["origen_datos"] = "Serie sintética (error al leer archivo)"

    resultado = simular_aprovechamiento(
        precip_df,
        area_captacion_m2=area,
        coef_escorrentia=coef_esc,
        eficiencia=eficiencia,
        capacidad_tanque_m3=capacidad,
        consumo_diario_m3=consumo,
        stock_inicial_m3=stock0,
    )
    kpis = calcular_kpis(resultado)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            "Total agua ahorrada (m³)",
            f"{kpis['total_ahorrado_m3']:.2f}",
            help="Volumen de demanda cubierto con agua captada (no con red potable).",
        )
    with c2:
        st.metric(
            "Total agua potable usada (m³)",
            f"{kpis['total_potable_m3']:.2f}",
            help="Suplemento de red cuando el tanque no cubre el consumo diario.",
        )
    with c3:
        st.metric(
            "Eficiencia de cobertura (%)",
            f"{kpis['eficiencia_pct']:.1f}",
            help="Agua ahorrada / demanda total × 100.",
        )
    st.caption(f"Origen de precipitación: {st.session_state.get('origen_datos', '—')}")

    st.plotly_chart(grafico_nivel_tanque(resultado), use_container_width=True)

    st.subheader("Tabla de resultados")
    display_df = resultado.copy()
    display_df[COL_FECHA] = pd.to_datetime(display_df[COL_FECHA]).dt.strftime("%Y-%m-%d")

    st.dataframe(display_df, use_container_width=True, height=320)

    csv_bytes = resultado.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Descargar resultados (CSV)",
        data=csv_bytes,
        file_name=f"simulacion_agua_lluvia_UCC_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

    with st.expander("Lógica de stocks y flujos (resumen)"):
        st.markdown(
            """
            - **Stock**: estado del tanque al **final** de cada día, tras captación, rebalse y consumo.
            - **Captación**: entra al tanque según lámina de lluvia, área y coeficientes.
            - **Rebose**: excedente respecto a la capacidad; no queda almacenado.
            - **Consumo**: salida fija diaria; primero se usa el stock; el déficit es **agua potable suplementaria**.
            """
        )


if __name__ == "__main__":
    main()
