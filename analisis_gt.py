import os
import argparse
import numpy as np
import pandas as pd
from skimage import io, measure, morphology, segmentation, util
from skimage.measure import regionprops
from scipy import ndimage as ndi
import matplotlib

#!/usr/bin/env python3
"""
analisis_gt.py

Analiza cuantitativamente un ground truth de células (imagen etiquetada o máscara binaria)
y genera métricas por célula, sugerencias de ampliación (dilatación) para hacer regiones
más circulares y estrategias de colocación de semillas para watershed.

Salida:
 - CSV con métricas por objeto
 - report.md con resumen estadístico y recomendaciones
 - gráficos PNG (histogramas, scatter)
 - opcional: imágenes con semillas sugeridas y mapas de dilatación

Uso:
 python3 analisis_gt.py --input path/to/gt.png --outdir results --circularity_target 0.85

"""
import matplotlib.pyplot as plt

def load_label_image(path):
    img = io.imread(path)
    
    img = np.asarray(img)
    if np.issubdtype(img.dtype, np.floating):
        img = (img > 0.5).astype(np.uint8)
    # si binaria, etiquetar
    if img.ndim == 2 and img.max() in (0, 1):
        labeled = measure.label(img, connectivity=1)
    else:
        # asumir imagen etiquetada (enteros)
        labeled = img.astype(np.int32)
    return labeled

def analyze_labels(labeled):
    props = regionprops(labeled)
    rows = []
    for p in props:
        label = p.label
        area = p.area
        perimeter = p.perimeter if p.perimeter > 0 else 1.0
        circularity = 4 * np.pi * area / (perimeter**2)
        eq_radius = np.sqrt(area / np.pi)
        centroid = p.centroid
        bbox = p.bbox
        eccentricity = p.eccentricity
        solidity = p.solidity
        extent = p.extent
        convex_area = p.convex_area
        major = p.major_axis_length
        minor = p.minor_axis_length
        orientation = p.orientation

        # máscara del objeto
        mask = (labeled == label)
        # Distance transform dentro del objeto:
        dt = ndi.distance_transform_edt(mask)
        max_inscribed_radius = float(dt.max())  # radio del mayor círculo inscrito
        # distancia al punto más lejano desde el centroide
        coords = p.coords
        cy, cx = centroid
        dists = np.sqrt((coords[:,0]-cy)**2 + (coords[:,1]-cx)**2)
        max_dist_from_centroid = float(dists.max())
        mean_dist_from_centroid = float(dists.mean())

        # estimación de radio de dilatación para aproximar a "círculo" hasta el punto más lejano
        # R_current = eq_radius; R_target = max_dist_from_centroid
        suggested_dilation_radius = max(0.0, max_dist_from_centroid - eq_radius)

        # semilla segura: centro del mayor círculo inscrito (coordenadas del máximo DT)
        max_pos = np.array(np.unravel_index(np.argmax(dt), dt.shape))
        seed_coord = (int(max_pos[0]), int(max_pos[1]))
        # número sugerido de semillas:
        # si solidity alta y circularity alta -> 1; si objeto grande or elongated -> consider multiples
        suggested_n_seeds = 1
        if area > 2000 or eccentricity > 0.9 or circularity < 0.5:
            suggested_n_seeds = 2
        if area > 5000:
            suggested_n_seeds = max(suggested_n_seeds, 3)

        rows.append({
            "label": label,
            "area_px": area,
            "perimeter_px": perimeter,
            "circularity": circularity,
            "equivalent_radius_px": eq_radius,
            "max_dist_from_centroid_px": max_dist_from_centroid,
            "mean_dist_from_centroid_px": mean_dist_from_centroid,
            "max_inscribed_radius_px": max_inscribed_radius,
            "suggested_dilation_radius_px": suggested_dilation_radius,
            "seed_row": seed_coord[0],
            "seed_col": seed_coord[1],
            "suggested_n_seeds": suggested_n_seeds,
            "eccentricity": eccentricity,
            "solidity": solidity,
            "extent": extent,
            "convex_area": convex_area,
            "major_axis_length": major,
            "minor_axis_length": minor,
            "orientation": orientation
        })
    df = pd.DataFrame(rows)
    return df

def summarize_and_report(df, outdir, circularity_target=0.85):
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, "metrics_per_cell.csv")
    df.to_csv(csv_path, index=False)

    # resumen estadístico
    numeric = df.select_dtypes(include=[np.number])
    summary = numeric.describe(percentiles=[0.25,0.5,0.75,0.9]).T
    summary_path = os.path.join(outdir, "summary_metrics.csv")
    summary.to_csv(summary_path)

    # recomendaciones agregadas
    median_dilation = float(np.nanmedian(df["suggested_dilation_radius_px"]))
    p90_dilation = float(np.nanpercentile(df["suggested_dilation_radius_px"], 90))
    mean_circ = float(np.nanmean(df["circularity"]))
    median_circ = float(np.nanmedian(df["circularity"]))
    proportion_high_circ = float((df["circularity"] >= circularity_target).mean())

    # generar gráficas
    plt.figure(figsize=(6,4))
    plt.hist(df["circularity"].dropna(), bins=40, color='C0', edgecolor='k')
    plt.axvline(circularity_target, color='r', linestyle='--', label=f'target {circularity_target}')
    plt.xlabel("Circularidad")
    plt.ylabel("N objetos")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "hist_circularity.png"))
    plt.close()

    plt.figure(figsize=(6,4))
    plt.hist(df["suggested_dilation_radius_px"].dropna(), bins=40, color='C2', edgecolor='k')
    plt.xlabel("Radio de dilatación sugerido (px)")
    plt.ylabel("N objetos")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "hist_suggested_dilation.png"))
    plt.close()

    # scatter circularidad vs área
    plt.figure(figsize=(6,4))
    plt.scatter(df["area_px"], df["circularity"], s=10, alpha=0.6)
    plt.xscale('log')
    plt.xlabel("Area (px, log)")
    plt.ylabel("Circularidad")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "scatter_area_vs_circularity.png"))
    plt.close()

    # Reporte Markdown (es breve y directo)
    report_lines = []
    report_lines.append("# Informe cuantitativo del Ground Truth\n")
    report_lines.append("Resumen estadístico (ver summary_metrics.csv)\n")
    report_lines.append(f"- Numero de objetos analizados: {len(df)}\n")
    report_lines.append(f"- Circularidad media: {mean_circ:.3f}, mediana: {median_circ:.3f}\n")
    report_lines.append(f"- Fracción de objetos con circularidad >= {circularity_target}: {proportion_high_circ:.3f}\n")
    report_lines.append(f"- Radio de dilatación sugerido (mediana): {median_dilation:.2f} px\n")
    report_lines.append(f"- Radio de dilatación sugerido (90perc): {p90_dilation:.2f} px\n")
    report_lines.append("\n## Recomendaciones automáticas para el pipeline\n")
    report_lines.append("1. Expansión de regiones (dilatación antes de watershed):\n")
    report_lines.append("   - Aplicar una dilatación con radio r = median(suggested_dilation_radius_px) como punto de partida\n")
    report_lines.append("   - Para imágenes más conservadoras usar r = ceil(median) ; para asegurar unión de concavidades grandes usar r = ceil(p90)\n")
    report_lines.append("   - Alternativa: usar un cierre morfológico (closing) con elemento estructurante disco de radio r para rellenar concavidades\n")
    report_lines.append("2. Posicionamiento de semillas para watershed:\n")
    report_lines.append("   - Si solidity alta (>0.9) y circularity alta (>0.7): usar el centroide o el máximo del distance transform (seed_row/seed_col)\n")
    report_lines.append("   - Si objetos grandes/elongados o circularity baja: usar múltiples semillas. Se sugiere generar picos locales en el distance transform\n")
    report_lines.append("     con separación mínima ~ max_inscribed_radius/2 o usando watershed sobre -distance_transform con h-maxima para control de núcleos.\n")
    report_lines.append("3. Parámetros sugeridos detectados automáticamente:\n")
    report_lines.append(f"   - radio_dilatacion_mediana = {median_dilation:.2f} px\n")
    report_lines.append(f"   - radio_dilatacion_p90 = {p90_dilation:.2f} px\n")
    report_lines.append("\n## Archivos generados\n")
    report_lines.append("- metrics_per_cell.csv: métricas por objeto\n")
    report_lines.append("- summary_metrics.csv: resumen estadístico\n")
    report_lines.append("- hist_circularity.png, hist_suggested_dilation.png, scatter_area_vs_circularity.png\n")

    report_path = os.path.join(outdir, "report.md")
    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))

    return {
        "csv": csv_path,
        "summary_csv": summary_path,
        "report_md": report_path,
        "median_dilation": median_dilation,
        "p90_dilation": p90_dilation,
        "mean_circularity": mean_circ
    }

def visualize_seeds(labeled, df, outdir):
    # dibujar semillas sobre una imagen de etiquetas convertida a color
    cmap = matplotlib.cm.get_cmap('tab20')
    label_img = segmentation.mark_boundaries(np.zeros_like(labeled, dtype=float), labeled, color=(1,1,1))
    fig, ax = plt.subplots(1,1, figsize=(8,8))
    ax.imshow(label_img, cmap='gray')
    for _, row in df.iterrows():
        r,c = int(row['seed_row']), int(row['seed_col'])
        ax.plot(c, r, 'ro', markersize=3)
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "seeds_overlay.png"), dpi=150)
    plt.close()

def main():
    parser = argparse.ArgumentParser(description="Analisis cuantitativo del ground truth de células")
    parser.add_argument('--input', '-i', required=True, help="Imagen de ground truth (etiquetada o binaria)")
    parser.add_argument('--outdir', '-o', default="gt_analysis_results", help="Directorio de salida")
    parser.add_argument('--circularity_target', type=float, default=0.85, help="Umbral objetivo de circularidad")
    args = parser.parse_args()

    labeled = load_label_image(args.input)
    df = analyze_labels(labeled)
    results = summarize_and_report(df, args.outdir, circularity_target=args.circularity_target)
    visualize_seeds(labeled, df, args.outdir)

    print("Análisis completado.")
    print("Resultados:", results["report_md"])

if __name__ == '__main__':
    main()