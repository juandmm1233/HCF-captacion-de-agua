# Explicación del proyecto y fórmulas matemáticas

Este proyecto es un **simulador de aprovechamiento de agua lluvia** para la UCC, construido con **Python + Streamlit**.

## Cómo funciona el proyecto

- La interfaz está en `app.py` y el motor matemático está en `simulacion.py`.
- El usuario define parámetros físicos y económicos:
  - área de captación,
  - coeficiente de escorrentía,
  - eficiencia del sistema,
  - capacidad del tanque,
  - consumo diario,
  - tarifa del agua,
  - inversión inicial (opcional).
- La lluvia se toma de:
  - un archivo `CSV/Excel` cargado por el usuario, o
  - una serie sintética generada por el sistema.
- La simulación se ejecuta **día a día**:
  1. calcula captación,
  2. actualiza stock,
  3. calcula rebose si hay excedente,
  4. descuenta consumo,
  5. calcula agua potable suplementaria si falta agua en tanque.
- Después calcula indicadores hidráulicos y económicos, y los muestra en KPIs, tablas y gráficos.

---

## Operación 1: Captación diaria

### Fórmula

\[
C_i = \frac{P_i}{1000}\cdot A \cdot \phi \cdot \eta
\]

### Variables

- `C_i`: captación del día `i` en m³.
- `P_i`: precipitación del día `i` en mm.
- `A`: área de captación en m².
- `φ` (`phi`): coeficiente de escorrentía (adimensional, entre 0 y 1).
- `η` (`eta`): eficiencia del sistema (adimensional, entre 0 y 1).
- `1000`: factor de conversión de mm a m.

---

## Operación 2: Actualización de stock antes de consumo

### Fórmula

\[
S'_i = S_{i-1} + C_i
\]

### Variables

- `S'_i`: stock temporal del tanque el día `i` antes de aplicar rebose/consumo.
- `S_{i-1}`: stock final del día anterior.
- `C_i`: captación del día `i`.

---

## Operación 3: Rebose del tanque

### Fórmulas

\[
R_i = \max(0,\; S'_i - V_{max})
\]

\[
\tilde S_i = \min(S'_i,\; V_{max})
\]

### Variables

- `R_i`: volumen rebosado el día `i` (m³).
- `S'_i`: stock temporal antes de límite de capacidad.
- `V_max`: capacidad máxima del tanque (m³).
- `\tilde S_i`: stock limitado por capacidad (stock disponible para consumo).

---

## Operación 4: Consumo diario y suplemento de red

### Fórmulas

\[
G_i = \max(0,\; D - \tilde S_i)
\]

\[
S_i = \max(0,\; \tilde S_i - D)
\]

### Variables

- `G_i`: agua potable suplementaria (déficit cubierto con red) en m³ el día `i`.
- `D`: consumo diario equivalente (m³/día).
- `\tilde S_i`: stock disponible antes de consumo.
- `S_i`: stock final del tanque al cierre del día `i`.

---

## Operación 5: Agua lluvia consumida

### Fórmula

\[
L_i = D - G_i
\]

### Variables

- `L_i`: volumen de demanda del día `i` cubierto con agua lluvia (m³).
- `D`: consumo diario total del día `i`.
- `G_i`: agua potable suplementaria de red del día `i`.

---

## Operación 6: Ahorro económico diario y acumulado

### Fórmulas

\[
Ahorro_i = L_i \cdot T
\]

\[
Ahorro\_{acum}(n) = \sum_{i=1}^{n} Ahorro_i
\]

\[
Lluvia\_{acum}(n) = \sum_{i=1}^{n} L_i
\]

### Variables

- `Ahorro_i`: ahorro económico diario en COP.
- `L_i`: agua lluvia consumida en el día `i` (m³).
- `T`: tarifa del agua en COP/m³.
- `Ahorro_acum(n)`: ahorro acumulado hasta el día `n`.
- `Lluvia_acum(n)`: agua lluvia acumulada consumida hasta el día `n`.

---

## Operación 7: Ahorro anual proyectado

### Fórmula

\[
Ahorro_{anual} = \left(\sum_{i=1}^{N} Ahorro_i\right)\cdot \frac{365}{N}
\]

### Variables

- `Ahorro_anual`: ahorro anual proyectado en COP/año.
- `N`: número de días simulados.
- `Ahorro_i`: ahorro diario observado.
- `365/N`: factor de anualización del periodo simulado.

---

## Operación 8: Punto de equilibrio (Payback simple)

### Fórmula

\[
Payback_{años} = \frac{I}{Ahorro_{anual}}
\]

### Variables

- `Payback_años`: años estimados para recuperar la inversión.
- `I`: inversión inicial en COP.
- `Ahorro_anual`: ahorro anual proyectado en COP/año.

> Condición de validez: `I > 0` y `Ahorro_anual > 0`.

---

## Operación 9: ROI anual simple

### Fórmula

\[
ROI_{anual}(\%) = \frac{Ahorro_{anual}}{I}\cdot 100
\]

### Variables

- `ROI_anual(%)`: retorno anual simple en porcentaje.
- `Ahorro_anual`: ahorro anual proyectado.
- `I`: inversión inicial.

> Nota: no incluye costos de operación/mantenimiento ni valor del dinero en el tiempo.

---

## Operación 10: Eficiencia de cobertura hídrica

### Fórmula

\[
Eficiencia(\%) = \frac{Demanda_{total} - Potable_{total}}{Demanda_{total}} \cdot 100
\]

### Variables

- `Demanda_total`: suma del consumo total del periodo (m³).
- `Potable_total`: suma del suplemento de red del periodo (m³).
- `Demanda_total - Potable_total`: agua atendida por lluvia.
- `Eficiencia(%)`: porcentaje de cobertura de demanda con agua lluvia.

---

## Operación 11: (Opcional) Precipitación sintética del modelo

Cuando no se carga archivo, la lluvia diaria sintética se calcula con componente estacional y ruido:

\[
P \approx \max\left(8 + 6\sin\left(\frac{2\pi(doy-80)}{365}\right) + \Gamma(1.2,2.5) - 3,\; 0\right)
\]

Si el día está en temporada seca seleccionada:

\[
P_{seca} = P \cdot f_{seca}
\]

### Variables

- `P`: precipitación sintética diaria base (mm).
- `doy`: day-of-year (día del año, 1..365).
- `Γ(1.2, 2.5)`: ruido aleatorio Gamma (shape=1.2, scale=2.5).
- `f_seca`: factor de reducción en meses secos (0 a 1).
- `P_seca`: precipitación final ajustada por estación seca.

---

## Variables principales del código (nombres usados en `simulacion.py`)

- `area_captacion_m2` = `A`
- `coef_escorrentia` = `φ`
- `eficiencia` = `η`
- `capacidad_tanque_m3` = `V_max`
- `consumo_diario_m3` = `D`
- `stock_inicial_m3` = stock al día 0
- `Captacion_m3` = `C_i`
- `Rebose_m3` = `R_i`
- `Agua_Potable_Suple_m3` = `G_i`
- `Stock_Tanque_m3` = `S_i`
- `Agua_Lluvia_Consumida_m3` = `L_i`
- `Ahorro_Diario_COP` = `Ahorro_i`
- `Ahorro_Acumulado_COP` = `Ahorro_acum`
- `Agua_Lluvia_Acumulada_m3` = `Lluvia_acum`
- `tarifa_cop_m3` = `T`
- `inversion_cop` = `I`

