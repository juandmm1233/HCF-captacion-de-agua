"""
Aplicación Streamlit — Simulación de aprovechamiento de agua lluvia (UCC).

La lógica de simulación, datos y gráficos está en ``simulacion.py``;
este archivo solo define la interfaz web.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from simulacion import (
    COL_FECHA,
    COL_PRECIP,
    agregar_columnas_lluvia_y_economia,
    ahorro_anual_proyectado_cop,
    build_excel_captacion_rebose_y_completo,
    calcular_kpis,
    cargar_precipitaciones,
    filtrar_precip_por_rango,
    formato_cop_miles,
    formato_miles_colombiano,
    generar_precipitacion_sintetica,
    grafico_ahorro_acumulado_dual,
    grafico_captacion_vs_rebose,
    grafico_nivel_tanque,
    punto_equilibrio_anos,
    roi_anual_simple_pct,
    simular_aprovechamiento,
)


# Límite de días por simulación para evitar series excesivamente largas en el navegador.
_MAX_DIAS_SIMULACION = 365 * 15


def main() -> None:
    año_actual = date.today().year
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
        /* Tarjetas KPI: fondo claro + texto oscuro (el tema oscuro de Streamlit dejaba cifras ilegibles). */
        div[data-testid="stMetric"] {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 12px 16px;
            color: #0f172a;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] p,
        div[data-testid="stMetric"] span,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"],
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
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
        st.subheader("Economía")
        tarifa_cop_m3 = st.number_input(
            "Tarifa de agua (COP/m³)",
            min_value=0.0,
            value=4800.0,
            step=100.0,
            format="%.0f",
        )
        inversion_cop = st.number_input(
            "Costo de inversión inicial (COP)",
            min_value=0.0,
            value=0.0,
            step=500_000.0,
            format="%.0f",
            help="Para estimar punto de equilibrio (payback) y ROI anual simple.",
        )

        st.divider()
        st.subheader("Datos de precipitación")
        rango_txt = f"{_MAX_DIAS_SIMULACION:,}".replace(",", ".")
        fecha_desde = st.date_input(
            "Fecha inicial del periodo",
            value=date(año_actual, 1, 1),
            help="Primer día incluido en la simulación (datos de archivo o serie sintética).",
        )
        fecha_hasta = st.date_input(
            "Fecha final del periodo",
            value=date(año_actual, 12, 31),
            help="Último día incluido. El periodo total no puede superar "
            f"{rango_txt} días (se acorta automáticamente).",
        )
        if fecha_hasta < fecha_desde:
            st.sidebar.warning(
                "La fecha final es anterior a la inicial; se usará un solo día (la fecha inicial)."
            )
            fecha_hasta = fecha_desde
        dias_periodo = (fecha_hasta - fecha_desde).days + 1
        if dias_periodo > _MAX_DIAS_SIMULACION:
            st.sidebar.warning(
                f"Periodo limitado a {_MAX_DIAS_SIMULACION:,} días; se ajustó la fecha final.".replace(
                    ",", "."
                )
            )
            fecha_hasta = fecha_desde + timedelta(days=_MAX_DIAS_SIMULACION - 1)
            dias_periodo = _MAX_DIAS_SIMULACION
        fecha_inicio_sim = datetime.combine(fecha_desde, time.min)

        archivo = st.file_uploader(
            "Subir CSV o Excel",
            type=["csv", "xlsx", "xls"],
            help=f"Columnas requeridas: '{COL_FECHA}' y '{COL_PRECIP}' (o nombres equivalentes).",
        )

    etiqueta_periodo = f"{fecha_desde.isoformat()} → {fecha_hasta.isoformat()} ({dias_periodo} días)"

    # Datos: archivo o sintéticos
    try:
        if archivo is not None:
            precip_df = filtrar_precip_por_rango(cargar_precipitaciones(archivo), fecha_desde, fecha_hasta)
            st.session_state["origen_datos"] = f"Archivo: {archivo.name} · {etiqueta_periodo}"
        else:
            precip_df = generar_precipitacion_sintetica(
                dias=dias_periodo,
                fecha_inicio=fecha_inicio_sim,
            )
            st.session_state["origen_datos"] = f"Serie sintética · {etiqueta_periodo}"
    except Exception as e:
        st.error(str(e))
        precip_df = generar_precipitacion_sintetica(
            dias=dias_periodo,
            fecha_inicio=fecha_inicio_sim,
        )
        st.session_state["origen_datos"] = f"Serie sintética (error al leer archivo) · {etiqueta_periodo}"

    if precip_df.empty:
        st.error(
            "No hay datos de precipitación en el periodo seleccionado. "
            "Amplíe el rango de fechas o revise el archivo."
        )
        st.stop()

    resultado = simular_aprovechamiento(
        precip_df,
        area_captacion_m2=area,
        coef_escorrentia=coef_esc,
        eficiencia=eficiencia,
        capacidad_tanque_m3=capacidad,
        consumo_diario_m3=consumo,
        stock_inicial_m3=stock0,
    )
    resultado_eco = agregar_columnas_lluvia_y_economia(resultado, tarifa_cop_m3)
    kpis = calcular_kpis(resultado)
    ahorro_anual = ahorro_anual_proyectado_cop(resultado_eco)
    payback = punto_equilibrio_anos(inversion_cop, ahorro_anual)
    roi_pct = roi_anual_simple_pct(inversion_cop, ahorro_anual)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Total agua ahorrada (m³)",
            formato_miles_colombiano(kpis["total_ahorrado_m3"], decimales=2),
            help="Volumen de demanda cubierto con agua captada (no con red potable).",
        )
    with c2:
        st.metric(
            "Total agua potable usada (m³)",
            formato_miles_colombiano(kpis["total_potable_m3"], decimales=2),
            help="Suplemento de red cuando el tanque no cubre el consumo diario.",
        )
    with c3:
        st.metric(
            "Eficiencia de cobertura (%)",
            formato_miles_colombiano(kpis["eficiencia_pct"], decimales=1),
            help="Agua ahorrada / demanda total × 100.",
        )
    with c4:
        st.metric(
            "Ahorro total anual proyectado (COP)",
            formato_cop_miles(ahorro_anual),
            help="Escala el ahorro monetario del periodo simulado a 365 días, "
            "con la tarifa indicada.",
        )

    e1, e2, e3 = st.columns(3)
    with e1:
        st.metric("Inversión inicial (COP)", formato_cop_miles(inversion_cop))
    with e2:
        st.metric(
            "Punto de equilibrio (años)",
            f"{payback:.2f}".replace(".", ",") if payback is not None else "—",
            help="Inversión ÷ ahorro anual proyectado.",
        )
    with e3:
        st.metric(
            "ROI anual simple (%)",
            formato_miles_colombiano(roi_pct, decimales=1) if roi_pct is not None else "—",
            help="Ahorro anual proyectado ÷ inversión × 100. No incluye TRM ni costos de O&M.",
        )

    st.caption(f"Origen de precipitación: {st.session_state.get('origen_datos', '—')}")

    st.subheader("Evolución del nivel del tanque")
    st.plotly_chart(grafico_nivel_tanque(resultado_eco), use_container_width=True)

    st.subheader("Captación vs. rebalse")
    st.caption("Barras agrupadas: captación diaria y volumen rebosado.")
    st.plotly_chart(grafico_captacion_vs_rebose(resultado_eco), use_container_width=True)
    excel_bytes = build_excel_captacion_rebose_y_completo(resultado_eco)
    st.download_button(
        label="Descargar Excel (captación/rebalse y resultados completos)",
        data=excel_bytes,
        file_name=f"captacion_rebalse_UCC_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.subheader("Economía: ahorro acumulado")
    st.caption("Serie dual: volumen de lluvia utilizada acumulada (m³) y ahorro acumulado (COP).")
    st.plotly_chart(grafico_ahorro_acumulado_dual(resultado_eco), use_container_width=True)

    st.subheader("Tabla de resultados")
    display_df = resultado_eco.copy()
    display_df[COL_FECHA] = pd.to_datetime(display_df[COL_FECHA]).dt.strftime("%Y-%m-%d")

    st.dataframe(display_df, use_container_width=True, height=320)

    csv_bytes = resultado_eco.to_csv(index=False).encode("utf-8-sig")
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
            - **Agua lluvia consumida**: volumen diario de demanda cubierto sin recurrir a la red.
            - **Ahorro diario (COP)**: agua lluvia consumida × tarifa; el **ahorro acumulado** es la suma en el tiempo.
            - **Punto de equilibrio**: reparto simple de la inversión inicial sobre el ahorro anualizado.
            """
        )


if __name__ == "__main__":
    main()
