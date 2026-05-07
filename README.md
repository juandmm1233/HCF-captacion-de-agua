# Aprovechamiento de agua lluvia — UCC (Streamlit)

Simulación dinámica de balance de masas (tanque, captación, rebalse, consumo y suplemento de red) con capa económica en pesos colombianos y gráficos interactivos (Plotly).

**Documentación del código:** [docs/DOCUMENTACION.md](docs/DOCUMENTACION.md)

## Ejecución local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Abre el navegador en `http://localhost:8501`.

## Docker

### Construir la imagen

```bash
docker build -t ucc-agua-lluvia .
```

### Ejecutar el contenedor

```bash
docker run --rm -p 8501:8501 ucc-agua-lluvia
```

Accede a **http://localhost:8501**.

### Docker Compose

```bash
docker build -t ucc-agua-lluviad
```

Misma URL; el servicio queda definido en `docker-compose.yml`.

### Notas

- Streamlit escucha en `0.0.0.0:8501` dentro del contenedor para aceptar conexiones desde el host.
- El archivo `app.py` y las dependencias se copian en la imagen; los datos se cargan desde el navegador (subida de CSV/Excel) o se usan datos sintéticos.

## Estructura

| Ruta | Descripción |
|------|-------------|
| `app.py` | Aplicación Streamlit y motor de simulación |
| `requirements.txt` | Dependencias Python |
| `docs/DOCUMENTACION.md` | Diseño, fórmulas y referencia de funciones |
| `Dockerfile` / `docker-compose.yml` | Contenedorización |
