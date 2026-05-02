# Documentación técnica — Simulación de aprovechamiento de agua lluvia (UCC)

Aplicación **monolítica** en un solo módulo (`app.py`): datos → simulación hidráulica → capa económica → visualización Streamlit.

## Requisitos

- Python 3.10 o superior (el `Dockerfile` usa 3.12).
- Dependencias listadas en `requirements.txt`.

## Flujo general de ejecución

1. **Entrada de parámetros** (`main()`, barra lateral): físicos del sistema, económicos y opcionalmente un archivo de precipitación.
2. **Serie de precipitación**: CSV/Excel con columnas normalizadas a `Fecha` y `Precipitacion_mm`, o serie **sintética** de 365 días si no hay archivo.
3. **Simulación** `simular_aprovechamiento()`: bucle día a día que actualiza el **stock** del tanque.
4. **Post-proceso económico** `agregar_columnas_lluvia_y_economia()`: ahorros diarios y acumulados en m³ y COP.
5. **KPIs y gráficos**: `calcular_kpis()`, funciones `grafico_*()`, tabla y exportaciones CSV/Excel.

```mermaid
flowchart LR
    A[Precipitación] --> B[simular_aprovechamiento]
    B --> C[resultado DataFrame]
    C --> D[agregar_columnas_lluvia_y_economia]
    D --> E[Streamlit KPIs + Plotly]
```

---

## Datos de precipitación

| Función | Rol |
|---------|-----|
| `generar_precipitacion_sintetica()` | Construye fechas + mm/día con componente estacional y ruido (Gamma). Semilla fija por defecto para resultados reproducibles. |
| `normalizar_columnas()` | Renombra variantes (`fecha`, `precip`, etc.) a `Fecha` y `Precipitacion_mm`, convierte tipos y ordena cronológicamente. |
| `cargar_precipitaciones()` | Lee el objeto subido por Streamlit: `.csv` con `read_csv`, `.xlsx`/`.xls` con `read_excel`, luego normaliza. |

---

## Motor de simulación: stocks y flujos

Función: **`simular_aprovechamiento(...)`**

Para cada día \(i\) (en orden):

1. **Captación (m³/día)**  
   \[
   C_i = \frac{P_i}{1000} \cdot A \cdot \phi \cdot \eta
   \]  
   donde \(P_i\) es precipitación en mm, \(A\) área de captación (m²), \(\phi\) coeficiente de escorrentía y \(\eta\) eficiencia del sistema.

2. **Actualización previa al consumo**  
   \(S' = S_{i-1} + C_i\)

3. **Rebose**  
   Si \(S' > V_{\max}\):  
   - `Rebose_m3` = \(S' - V_{\max}\)  
   - Stock tras rebalse = \(V_{\max}\)

4. **Consumo constante** \(D\) (m³/día)  
   - Si el stock \(\ge D\): se resta \(D\), suplemento de red = 0.  
   - Si no: `Agua_Potable_Suple_m3` = \(D - S\), stock final = 0.

5. **`Stock_Tanque_m3[i]`** = stock al **final** del día tras los pasos anteriores.

**Columnas generadas:** `Fecha`, `Precipitacion_mm`, `Captacion_m3`, `Rebose_m3`, `Consumo_m3`, `Agua_Potable_Suple_m3`, `Stock_Tanque_m3`.

---

## Capa económica

Función: **`agregar_columnas_lluvia_y_economia(resultado, tarifa_cop_m3)`**

- **`Agua_Lluvia_Consumida_m3`** = `Consumo_m3` − `Agua_Potable_Suple_m3` (demanda cubierta con agua captada, no con red).

- **`Ahorro_Diario_COP`** = `Agua_Lluvia_Consumida_m3` × tarifa (COP/m³).

- **`Ahorro_Acumulado_COP`**, **`Agua_Lluvia_Acumulada_m3`**: sumas acumuladas (pandas `cumsum`).

**Anualización** (`ahorro_anual_proyectado_cop`):  
\[
\text{Ahorro anual} = \Big(\sum_i \text{Ahorro\_Diario\_COP}_i\Big) \cdot \frac{365}{N}
\]  
con \(N\) = número de días simulados. Así un periodo distinto de un año se extrapola a escala anual.

**Punto de equilibrio** (`punto_equilibrio_anos`):  
\[
\text{Años} = \frac{\text{Inversión}}{\text{Ahorro anual proyectado}}
\]  
solo si inversión y ahorro anual son mayores que cero.

**ROI anual simple** (`roi_anual_simple_pct`):  
\[
\text{ROI \%} = \frac{\text{Ahorro anual proyectado}}{\text{Inversión}} \times 100
\]  
No incluye costos de operación ni valor del dinero en el tiempo.

---

## KPIs hidráulicos

**`calcular_kpis(resultado)`** (sobre el DataFrame *sin* columnas económicas, solo hidráulicas):

- **Total agua ahorrada (m³)**: \(\sum D_i - \sum \text{Suple}_i\)
- **Total agua potable usada (m³)**: \(\sum \text{Suple}_i\)
- **Eficiencia de cobertura (%)**: agua ahorrada / demanda total × 100

---

## Visualización (Plotly)

| Función | Contenido |
|---------|-----------|
| `grafico_nivel_tanque()` | Serie temporal del volumen almacenado al cierre de cada día. |
| `grafico_captacion_vs_rebose()` | Barras agrupadas: captación diaria vs. rebalse. |
| `grafico_ahorro_acumulado_dual()` | Dos ejes Y: acumulado de m³ (lluvia utilizada) y acumulado en COP. |

**Formato de números:** `formato_miles_colombiano` y `formato_cop_miles` aplican separador de **miles con punto** y decimal con **coma**, alineado a uso local en Colombia para COP y métricas.

---

## Exportación

- **`build_excel_captacion_rebose_y_completo()`**: libro Excel en memoria (`BytesIO`) con:
  - hoja **Captacion_Rebose**;
  - hoja **Resultados_Completos** (todas las columnas de `resultado_eco`).

- CSV: codificación **UTF-8 con BOM** (`utf-8-sig`) para compatibilidad con Excel en Windows.

---

## Interfaz Streamlit (`main`)

- **`st.set_page_config`**: título, icono, diseño ancho.
- **Sidebar**: parámetros físicos, económicos, subida de archivo.
- Tras cada interacción, Streamlit **re-ejecuta** el script de arriba abajo; los cálculos son determinísticos salvo cambio de entradas.
- **`st.session_state`**: solo se usa para recordar el texto de origen de datos (archivo vs. sintético).

---

## Limitaciones y supuestos (explícitos)

- Consumo diario **constante**; no hay perfil horario dentro del día.
- La demanda se satisface **después** de captar y aplicar rebalse ese mismo día (orden fijo en el bucle).
- La anualización del ahorro monetario **proyecta** el periodo a 365 días; si el año hidrológico es atípico, el valor anual es orientativo.
- El ROI y el payback **no** descuentan O&M, energía, reemplazo de filtros, etc.

---

## Referencia rápida de archivos

| Archivo | Uso |
|---------|-----|
| `app.py` | Toda la lógica y la UI. |
| `requirements.txt` | Versiones mínimas de dependencias. |
| `Dockerfile` | Imagen para ejecutar Streamlit en contenedor. |
| `docker-compose.yml` | Arranque del servicio con un comando. |
| `docs/DOCUMENTACION.md` | Este documento. |

Instrucciones de instalación y Docker están en el [README](../README.md) del repositorio.
