"""
Módulo de simulación de aprovechamiento de agua lluvia — UCC.

Contiene la lógica de balance de masas (stocks y flujos), carga y normalización
de precipitaciones, métricas económicas, exportación Excel y construcción de gráficos
Plotly utilizados por la aplicación Streamlit.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# Constantes públicas — nombres canónicos de columnas tras normalizar datos
# COL_FECHA: columna de fechas unificada (variantes de entrada mapeadas en normalizar_columnas).
# COL_PRECIP: precipitación diaria en mm.
# -----------------------------------------------------------------------------

COL_FECHA = "Fecha"
COL_PRECIP = "Precipitacion_mm"


def generar_precipitacion_sintetica(
    dias: int = 365,
    fecha_inicio: datetime | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Construye una serie temporal sintética de precipitación diaria en mm.

    **Propósito:** permitir ejecutar la simulación sin subir un archivo cuando no hay datos reales.

    **Cómo funciona:**
        1. Se define un vector de fechas consecutivas de longitud ``dias`` a partir de
           ``fecha_inicio`` (si es ``None``, 1 de enero del **año calendario actual** en la zona horaria local).
        2. Para cada día se calcula el **día del año** y una componente **estacional** mediante
           un seno desplazado: simula un patrón húmedo/seco típico (mayor valores hacia mediados de año).
        3. Se suma **ruido positivo** con distribución Gamma (controlado por ``seed``) para
           variabilidad día a día; se resta un pequeño desplazamiento y se trunca en cero para
           que no existan precipitaciones negativas.

    **Retorno:** ``DataFrame`` con columnas ``COL_FECHA`` y ``COL_PRECIP``.
    """
    rng = np.random.default_rng(seed)
    if fecha_inicio is None:
        hoy = datetime.now().date()
        fecha_inicio = datetime(hoy.year, 1, 1, 0, 0, 0)
    fechas = [fecha_inicio + timedelta(days=i) for i in range(dias)]
    # Índice día del año 0..364 para patrón estacional (Colombia: mayor lluvia en mitad de año aprox.)
    doy = np.array([d.timetuple().tm_yday - 1 for d in fechas])
    estacional = 8.0 + 6.0 * np.sin(2 * np.pi * (doy - 80) / 365.0)
    ruido = rng.gamma(shape=1.2, scale=2.5, size=dias)
    precip = np.maximum(estacional + ruido - 3.0, 0.0)
    return pd.DataFrame({COL_FECHA: fechas, COL_PRECIP: precip})


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Unifica nombres de columnas de fecha y precipitación al esquema canónico.

    **Propósito:** aceptar CSV/Excel con encabezados flexibles (`date`, `precip`, `p_mm`, etc.).

    **Retorno:** copia ordenada lista para ``simular_aprovechamiento``.
    """
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
    """
    Lee un archivo CSV o Excel desde el objeto de subida típico de Streamlit.

    **Parámetros:**
        ``uploaded``: objeto con atributos ``.name`` y buffer legible por pandas.

    **Cómo funciona:**
        - Según la extensión del nombre (`csv`, `xlsx`, `xls`) se usa ``pd.read_csv`` o ``pd.read_excel``.
        - Cualquier otra extensión produce ``ValueError``.
        - El resultado se pasa por ``normalizar_columnas``.

    **Retorno:** mismo formato que ``normalizar_columnas``.
    """
    name = (uploaded.name or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded)
    else:
        raise ValueError("Formato no soportado. Use CSV o Excel (.csv, .xlsx).")
    return normalizar_columnas(df)


def filtrar_precip_por_rango(
    precip_df: pd.DataFrame,
    fecha_desde: date,
    fecha_hasta: date,
) -> pd.DataFrame:
    """
    Deja solo las filas cuya fecha de calendario está entre ``fecha_desde`` y ``fecha_hasta`` (inclusives).

    **Propósito:** acotar un archivo de precipitaciones al mismo periodo que el usuario elige en la interfaz.

    **Cómo funciona:** normaliza ``COL_FECHA`` a medianoche, compara con ``pd.Timestamp`` de los límites
    y devuelve un subconjunto ordenado con índice reiniciado. Si el ``DataFrame`` de entrada está vacío,
    devuelve una copia vacía con la misma estructura lógica.
    """
    if precip_df.empty:
        return precip_df.copy()
    out = precip_df.copy()
    ts = pd.to_datetime(out[COL_FECHA], errors="coerce")
    d0 = pd.Timestamp(fecha_desde)
    d1 = pd.Timestamp(fecha_hasta)
    mask = ts.dt.normalize().between(d0, d1, inclusive="both") & ts.notna()
    return out.loc[mask].reset_index(drop=True)


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
    Simulación día a día del tanque (stock) con entradas y salidas físicas.

    **Orden de operaciones cada día:**
        1. **Captación (m³/día):** la lámina equivalente es ``Precip(mm) / 1000``. El volumen bruto es
           lámina × área de captación × coeficiente de escorrentía × eficiencia del sistema.
        2. **Actualización del stock:** el stock aumenta con la captación. Si supera la capacidad,
           la diferencia se registra como **rebose** (pérdida) y el stock se capa al máximo.
        3. **Consumo:** demanda constante ``consumo_diario_m3``. Si el stock alcanza, se sustrae
           solo de él; si no, el faltante se etiqueta como **agua potable suplementaria** y el stock
           queda en 0.

    **Interpretación temporal:** cada fila corresponde a un día; ``Stock_Tanque_m3`` es el nivel
    al **cerrar** el día después de aplicar los tres pasos.

    **Columnas numéricas de salida:** ``Captacion_m3``, ``Rebose_m3``, ``Consumo_m3``
    (repetido el valor diario por fila para tablas claras),
    ``Agua_Potable_Suple_m3``, ``Stock_Tanque_m3``, más ``COL_FECHA`` y ``COL_PRECIP``.
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


def formato_miles_colombiano(val: float, decimales: int = 0, prefijo: str = "") -> str:
    """
    Formatea un número según convención visual colombiana común en la app.

    **Reglas:**
        - Con ``decimales == 0``: separador de miles con **punto**; parte entera redondeada.
        - Con ``decimales > 0``: miles con punto y **coma** como separador decimal (truco de reemplazo
          desde formato anglosajón ``format(..., ",.Nf")``).

    **Uso:** etiquetas de métricas, ejes de gráficos y ``hovertemplate`` en Plotly.
    """
    if decimales <= 0:
        entero = int(round(val))
        neg = entero < 0
        entero = abs(entero)
        grupo = f"{entero:,}".replace(",", ".")
        return f"{prefijo}{'-' if neg else ''}{grupo}"
    s_us = format(val, f",.{decimales}f")
    return prefijo + s_us.replace(",", "X").replace(".", ",").replace("X", ".")


def formato_cop_miles(val: float) -> str:
    """
    Atajo que formatea pesos colombianos sin decimales y con prefijo ``"$ "``.

    Delega en ``formato_miles_colombiano`` con ``decimales=0``.
    """
    return formato_miles_colombiano(val, decimales=0, prefijo="$ ")


def agregar_columnas_lluvia_y_economia(resultado: pd.DataFrame, tarifa_cop_m3: float) -> pd.DataFrame:
    """
    Enriquece el ``DataFrame`` de simulación con columnas de uso efectivo de lluvia y ahorro.

    **Derivaciones:**
        - ``Agua_Lluvia_Consumida_m3``: por día, volumen de la demanda cubierta sin recurrir a la red:
          ``Consumo_m3 - Agua_Potable_Suple_m3``.
        - ``Ahorro_Diario_COP``: ``Agua_Lluvia_Consumida_m3 * tarifa_cop_m3``.
        - ``Ahorro_Acumulado_COP`` y ``Agua_Lluvia_Acumulada_m3``: sumas acumuladas (``cumsum``).

    No modifica el argumento original: devuelve una **copia** con nuevas columnas.
    """
    out = resultado.copy()
    out["Agua_Lluvia_Consumida_m3"] = out["Consumo_m3"] - out["Agua_Potable_Suple_m3"]
    out["Ahorro_Diario_COP"] = out["Agua_Lluvia_Consumida_m3"] * tarifa_cop_m3
    out["Ahorro_Acumulado_COP"] = out["Ahorro_Diario_COP"].cumsum()
    out["Agua_Lluvia_Acumulada_m3"] = out["Agua_Lluvia_Consumida_m3"].cumsum()
    return out


def ahorro_anual_proyectado_cop(resultado_eco: pd.DataFrame) -> float:
    """
    Proyecta el ahorro monetario observado en el periodo simulado a un año civil (365 días).

    **Fórmula:** ``sum(Ahorro_Diario_COP) * (365 / N)``, donde ``N`` es la cantidad de filas/días.

    Si ``N <= 0`` devuelve ``0.0``. Sirve para comparar proyectos de distinta duración en término anual.
    """
    dias = len(resultado_eco)
    if dias <= 0:
        return 0.0
    return float(resultado_eco["Ahorro_Diario_COP"].sum()) * (365.0 / dias)


def punto_equilibrio_anos(inversion_cop: float, ahorro_anual_cop: float) -> float | None:
    """
    Calcula **payback simple**: años hasta recuperar la inversión con el ahorro anual proyectado.

    **Condiciones:** si la inversión es ≤ 0 o el ahorro anual ≤ 0, devuelve ``None`` (indicador de
    métricas no aplicables en la interfaz).

    Caso válido: ``inversion_cop / ahorro_anual_cop``.
    """
    if inversion_cop <= 0 or ahorro_anual_cop <= 0:
        return None
    return inversion_cop / ahorro_anual_cop


def roi_anual_simple_pct(inversion_cop: float, ahorro_anual_cop: float) -> float | None:
    """
    Retorno simple anualizado en porcentaje: ``100 * ahorro_anual_cop / inversion_cop``.

    **Advertencia conceptual:** no descuenta el valor temporal del dinero ni costos de operación/mantenimiento.

    Devuelve ``None`` si la inversión es ≤ 0.
    """
    if inversion_cop <= 0:
        return None
    return 100.0 * ahorro_anual_cop / inversion_cop


def build_excel_captacion_rebose_y_completo(resultado_eco: pd.DataFrame) -> bytes:
    """
    Construye un libro Excel en memoria con dos hojas.

    **Hoja "Captacion_Rebose":** fecha (como texto ``YYYY-MM-DD``), ``Captacion_m3``, ``Rebose_m3``.
    **Hoja "Resultados_Completos":** todas las columnas del ``DataFrame`` enriquecido, fechas igualmente
    como texto para interoperabilidad en Excel.

    Usa motor ``openpyxl`` mediante ``pd.ExcelWriter``. El **valor de retorno** son los ``bytes``
    completos del fichero (.xlsx) listos para descarga en Streamlit.
    """
    buf = io.BytesIO()
    cap_reb = resultado_eco[[COL_FECHA, "Captacion_m3", "Rebose_m3"]].copy()
    cap_reb[COL_FECHA] = pd.to_datetime(cap_reb[COL_FECHA]).dt.strftime("%Y-%m-%d")
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        cap_reb.to_excel(writer, index=False, sheet_name="Captacion_Rebose")
        full = resultado_eco.copy()
        full[COL_FECHA] = pd.to_datetime(full[COL_FECHA]).dt.strftime("%Y-%m-%d")
        full.to_excel(writer, index=False, sheet_name="Resultados_Completos")
    return buf.getvalue()


def calcular_kpis(resultado: pd.DataFrame) -> dict[str, float]:
    """
    Agrega KPIs físicos desde la tabla base de ``simular_aprovechamiento`` (antes de económicos).

    **Métricas:**
        - ``total_demanda_m3``: suma de ``Consumo_m3``.
        - ``total_potable_m3``: suma de suplementos de red.
        - ``total_ahorrado_m3``: demanda menos potable (volumen atendido con captación).
        - ``eficiencia_pct``: cobertura de la demanda con lluvia, porcentaje 0–100 (0 si demanda es 0).

    El diccionario devuelto usa las claves en inglés/snake_case para código de la interfaz existente.
    """
    total_demanda = float(resultado["Consumo_m3"].sum())
    total_potable = float(resultado["Agua_Potable_Suple_m3"].sum())
    total_ahorrado = total_demanda - total_potable
    eficiencia_pct = (100.0 * total_ahorrado / total_demanda) if total_demanda > 0 else 0.0
    return {
        "total_ahorrado_m3": total_ahorrado,
        "total_potable_m3": total_potable,
        "eficiencia_pct": eficiencia_pct,
        "total_demanda_m3": total_demanda,
    }


def _layout_grafico_responsive(
    fig: go.Figure,
    *,
    left: float = 40.0,
    right: float = 26.0,
    top: float = 54.0,
    bottom: float = 92.0,
) -> None:
    """
    Ajusta márgenes y leyenda horizontal **debajo** del eje X en figuras Plotly.

    """
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="center",
            x=0.5,
        ),
        margin=dict(l=left, r=right, t=top, b=bottom),
    )


def grafico_captacion_vs_rebose(resultado: pd.DataFrame) -> go.Figure:
    """
    Gráfico de barras agrupadas: captación diaria vs. rebalse diario (m³).

    **Entrada:** ``DataFrame`` con ``COL_FECHA``, ``Captacion_m3`` y ``Rebose_m3`` (p. ej. ``resultado_eco``).
    Aplica plantilla clara, ``hovermode="x unified"`` y ``_layout_grafico_responsive``.

    **Retorno:** ``go.Figure`` listo para ``st.plotly_chart``.
    """
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=resultado[COL_FECHA],
            y=resultado["Captacion_m3"],
            name="Captación (m³/día)",
            marker_color="#0ea5e9",
        )
    )
    fig.add_trace(
        go.Bar(
            x=resultado[COL_FECHA],
            y=resultado["Rebose_m3"],
            name="Rebose (m³/día)",
            marker_color="#94a3b8",
        )
    )
    fig.update_layout(
        title=None,
        barmode="group",
        xaxis_title="Fecha",
        yaxis_title="Volumen (m³)",
        template="plotly_white",
        hovermode="x unified",
    )
    _layout_grafico_responsive(fig)
    return fig


def grafico_ahorro_acumulado_dual(resultado_eco: pd.DataFrame) -> go.Figure:
    """
    Gráfico de líneas con **doble eje Y**: agua de lluvia utilizada acumulada (m³) y ahorro acumulado (COP).

    **Trazas:**
        - Eje izquierdo: ``Agua_Lluvia_Acumulada_m3`` (azul).
        - Eje derecho superpuesto: ``Ahorro_Acumulado_COP`` (verde).

    **Ticks personalizados:** se generan rejillas numéricas con ``linspace`` según máximos de cada serie
    y se formatean con ``formato_miles_colombiano`` / ``formato_cop_miles`` para coherencia con el resto
    del sitio. Los hovers usan ``customdata`` con el mismo formato.

    **Márgenes:** ``_layout_grafico_responsive`` con algo más de espacio inferior y derecho por las dos escalas.
    """
    fechas = resultado_eco[COL_FECHA]
    y_m3 = resultado_eco["Agua_Lluvia_Acumulada_m3"].astype(float)
    y_cop = resultado_eco["Ahorro_Acumulado_COP"].astype(float)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=fechas,
            y=y_m3,
            name="Agua lluvia utilizada acum. (m³)",
            mode="lines",
            line=dict(color="#0369a1", width=2),
            yaxis="y",
            customdata=[formato_miles_colombiano(float(v), decimales=2) + " m³" for v in y_m3],
            hovertemplate="%{x|%Y-%m-%d}<br>Acumulado: %{customdata}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=fechas,
            y=y_cop,
            name="Ahorro acumulado (COP)",
            mode="lines",
            line=dict(color="#059669", width=2),
            yaxis="y2",
            customdata=[formato_cop_miles(float(v)) for v in y_cop],
            hovertemplate="%{x|%Y-%m-%d}<br>Ahorro acum.: %{customdata}<extra></extra>",
        )
    )

    y1_max = float(np.nanmax(y_m3)) if len(y_m3) else 0.0
    y2_max = float(np.nanmax(y_cop)) if len(y_cop) else 0.0
    nt = 6
    t1 = np.linspace(0, max(y1_max * 1.05, 1e-9), nt)
    t2 = np.linspace(0, max(y2_max * 1.05, 1e-9), nt)

    fig.update_layout(
        title=None,
        xaxis_title="Fecha",
        template="plotly_white",
        hovermode="x unified",
        yaxis=dict(
            title=dict(text="Acumulado (m³)"),
            side="left",
            showgrid=True,
            tickmode="array",
            tickvals=t1,
            ticktext=[formato_miles_colombiano(float(t), decimales=2) for t in t1],
        ),
        yaxis2=dict(
            title=dict(text="Ahorro acumulado (COP)"),
            overlaying="y",
            side="right",
            showgrid=False,
            tickmode="array",
            tickvals=t2,
            ticktext=[formato_cop_miles(float(t)) for t in t2],
        ),
    )
    _layout_grafico_responsive(fig, left=55.0, right=72.0, bottom=100.0)
    return fig


def grafico_nivel_tanque(resultado: pd.DataFrame) -> go.Figure:
    """
    Serie temporal del **stock diario final** ``Stock_Tanque_m3`` con relleno bajo la curva.

    Muestra la evolución del volumen almacenado tras captación, rebalse y consumo cada día.
    Usa ``_layout_grafico_responsive`` para leyenda y márgenes móviles.

    **Retorno:** ``go.Figure`` listo para ``st.plotly_chart``.
    """
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
        title=None,
        xaxis_title="Fecha",
        yaxis_title="Volumen almacenado (m³)",
        template="plotly_white",
        hovermode="x unified",
    )
    _layout_grafico_responsive(fig)
    return fig
