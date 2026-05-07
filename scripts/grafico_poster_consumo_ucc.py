"""
Genera PNG de comparación consumo original vs aprovechamiento lluvia — UCC (póster).
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Datos ejemplo (m³/mes)
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
CONSUMO_ORIGINAL = [50, 45, 55, 60, 70, 80, 75, 65, 60, 55, 50, 48]
CONSUMO_LLUVIA = [35, 32, 38, 42, 49, 56, 52, 45, 42, 38, 35, 33]

# Salida: 1200 x 800 px
OUT_W, OUT_H = 1200, 800
DPI = 150
FIG_W, FIG_H = OUT_W / DPI, OUT_H / DPI

COLOR_ORIGINAL = "#1f77b4"
COLOR_LLUVIA = "#2ca02c"


def main() -> None:
    total_o = float(sum(CONSUMO_ORIGINAL))
    total_l = float(sum(CONSUMO_LLUVIA))
    ahorro_total_pct = (total_o - total_l) / total_o * 100.0
    # Promedio del % de ahorro mes a mes (opcional, coherente con "promedio")
    pct_mensual = [
        (o - l) / o * 100.0 for o, l in zip(CONSUMO_ORIGINAL, CONSUMO_LLUVIA, strict=True)
    ]
    ahorro_promedio_mensual_pct = float(np.mean(pct_mensual))

    # 1200 x 800 px a 150 dpi => 8" x 5,333..."
    fig, ax = plt.subplots(
        figsize=(FIG_W, FIG_H),
        dpi=DPI,
        facecolor="white",
    )
    ax.set_facecolor("white")

    x = np.arange(len(MESES))
    width = 0.36

    ax.bar(
        x - width / 2,
        CONSUMO_ORIGINAL,
        width,
        label="Consumo original (solo agua potable)",
        color=COLOR_ORIGINAL,
        edgecolor="white",
        linewidth=0.8,
        zorder=3,
    )
    ax.bar(
        x + width / 2,
        CONSUMO_LLUVIA,
        width,
        label="Consumo con aprovechamiento de agua de lluvia",
        color=COLOR_LLUVIA,
        edgecolor="white",
        linewidth=0.8,
        zorder=3,
    )

    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    ax.set_title(
        "Comparación: Consumo Original vs. Con Aprovechamiento de Agua Lluvia - UCC",
        fontsize=18,
        fontweight="bold",
        pad=18,
    )
    ax.set_xlabel("Mes", fontsize=14, labelpad=10)
    ax.set_ylabel("Volumen (m³/mes)", fontsize=14, labelpad=10)
    ax.set_xticks(x, MESES, fontsize=12)
    ax.tick_params(axis="y", labelsize=12)

    ax.yaxis.grid(True, linestyle="--", alpha=0.65, color="#888888", zorder=0)
    ax.set_axisbelow(True)

    ymax = max(max(CONSUMO_ORIGINAL), max(CONSUMO_LLUVIA))
    ax.set_ylim(0, math.ceil(ymax / 10.0) * 10 + 5)

    leg = ax.legend(
        fontsize=12,
        loc="upper left",
        frameon=True,
        fancybox=False,
        edgecolor="#cccccc",
    )
    leg.get_frame().set_facecolor("white")

    texto = (
        f"Ahorro anual respecto al consumo original: {ahorro_total_pct:.1f} % "
        f"({total_o:.0f} → {total_l:.0f} m³/año)\n"
        f"Ahorro promedio mensual (promedio de meses): {ahorro_promedio_mensual_pct:.1f} %"
    )
    fig.text(
        0.5,
        0.02,
        texto,
        ha="center",
        va="bottom",
        fontsize=13,
        fontweight="bold",
        color="#222222",
        linespacing=1.35,
    )

    subtitulo = "Universidad Cooperativa de Colombia — Sede El Salado (datos ilustrativos, m³/mes)"
    fig.suptitle(subtitulo, fontsize=11, color="#555555", y=0.96)

    fig.subplots_adjust(left=0.09, right=0.98, top=0.86, bottom=0.18)

    out_dir = Path(__file__).resolve().parent.parent / "docs" / "graficos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "consumo_ucc_original_vs_lluvia_poster.png"
    # Sin bbox_inches='tight' para mantener exactamente 1200×800 px
    fig.savefig(
        out_path,
        format="png",
        dpi=DPI,
        facecolor="white",
        edgecolor="none",
    )
    plt.close(fig)

    print(f"Guardado: {out_path}")
    print(f"Ahorro total anual: {ahorro_total_pct:.2f} %")
    print(f"Ahorro promedio mensual: {ahorro_promedio_mensual_pct:.2f} %")


if __name__ == "__main__":
    main()
