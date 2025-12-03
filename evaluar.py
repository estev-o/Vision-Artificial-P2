"""
Evaluación cuantitativa de segmentaciones (V3.3 final).

Flujo por imagen:
1) Carga predicción coloreada (`visualizaciones/<img>/4_coloreada.png`) y GT coloreado.
2) Binariza ambos y ajusta tamaño si difiere.
3) Calcula métricas píxel a píxel (F1/Dice, IoU, precisión, recall, accuracy).
4) Obtiene conteo/áreas GT desde XML (si existe) y conteo pred por CC.
5) Agrega métricas por imagen y genera `evaluacion.csv` con resumen global.
"""

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

XML_DIR = "Material Celulas/xml"
GT_COLORS_DIR = "Material Celulas/gt_colors"
OUTPUT_DIR = "visualizaciones"
RESULTADOS_CSV = "resultados.csv"  # entrada: lista de imágenes procesadas
OUTPUT_CSV = "evaluacion.csv"      # salida: métricas por imagen


def cargar_ground_truth_xml(ruta_xml: Path):
    """Devuelve (n_gt, lista_areas) desde el XML; si no existe, retorna (0, [])."""
    if not ruta_xml.exists():
        return 0, []
    try:
        tree = ET.parse(ruta_xml)
        regiones = tree.getroot().findall(".//Region")
        areas_gt = []
        for region in regiones:
            area_str = region.get("Area")
            if area_str:
                areas_gt.append(float(area_str))
        return len(areas_gt), areas_gt
    except Exception as e:
        print(f"Error al leer XML {ruta_xml}: {e}")
        return 0, []


def binarizar_imagen(imagen: np.ndarray) -> np.ndarray:
    """Convierte imagen coloreada a binaria (255 núcleos / 0 fondo)."""
    gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen
    _, binaria = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    return binaria


def calcular_metricas_pixel(pred_binaria: np.ndarray, gt_binaria: np.ndarray) -> dict:
    """Calcula F1(Dice), IoU, precision, recall, accuracy a nivel píxel."""
    pred = (pred_binaria > 0).astype(np.uint8)
    gt = (gt_binaria > 0).astype(np.uint8)

    tp = np.sum((pred == 1) & (gt == 1))
    fp = np.sum((pred == 1) & (gt == 0))
    fn = np.sum((pred == 0) & (gt == 1))
    tn = np.sum((pred == 0) & (gt == 0))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0.0

    return {
        "f1": f1,
        "iou": iou,
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def evaluar_imagen(nombre_imagen: str) -> dict | None:
    """Evalúa una imagen; retorna dict de métricas o None si falta algún archivo."""
    nombre_base = Path(nombre_imagen).stem

    ruta_pred = Path(OUTPUT_DIR) / nombre_base / "4_coloreada.png"
    if not ruta_pred.exists():
        print(f"⚠️  No existe predicción para {nombre_imagen}")
        return None
    pred_color = cv2.imread(str(ruta_pred))
    pred_binaria = binarizar_imagen(pred_color)

    ruta_gt = Path(GT_COLORS_DIR) / nombre_imagen
    if not ruta_gt.exists():
        print(f"⚠️  No existe GT para {nombre_imagen}")
        return None
    gt_color = cv2.imread(str(ruta_gt))
    gt_binaria = binarizar_imagen(gt_color)

    if pred_binaria.shape != gt_binaria.shape:
        pred_binaria = cv2.resize(pred_binaria, (gt_binaria.shape[1], gt_binaria.shape[0]))

    metricas = calcular_metricas_pixel(pred_binaria, gt_binaria)

    ruta_xml = Path(XML_DIR) / f"{nombre_base}.xml"
    num_nucleos_gt, areas_gt = cargar_ground_truth_xml(ruta_xml)

    num_labels, _ = cv2.connectedComponents(pred_binaria)
    num_nucleos_pred = max(num_labels - 1, 0)

    area_total_gt = areas_gt if areas_gt else [np.sum(gt_binaria > 0)]
    area_media_gt = float(np.mean(area_total_gt)) if area_total_gt else 0.0
    area_media_pred = float(np.sum(pred_binaria > 0) / num_nucleos_pred) if num_nucleos_pred > 0 else 0.0

    error_conteo_abs = abs(num_nucleos_pred - num_nucleos_gt)
    precision_conteo = 100 - (error_conteo_abs / num_nucleos_gt * 100) if num_nucleos_gt > 0 else 0.0

    return {
        "nombre": nombre_imagen,
        **metricas,
        "num_nucleos_gt": num_nucleos_gt,
        "num_nucleos_pred": num_nucleos_pred,
        "precision_conteo": precision_conteo,
        "area_media_gt": area_media_gt,
        "area_media_pred": area_media_pred,
    }


def evaluar_todas_imagenes():
    """Evalúa todas las imágenes listadas en resultados.csv y guarda evaluacion.csv."""
    if not Path(RESULTADOS_CSV).exists():
        print(f"❌ No existe {RESULTADOS_CSV}. Ejecuta primero la segmentación.")
        return

    with open(RESULTADOS_CSV, "r") as f:
        imagenes = [row["Imagen"] for row in csv.DictReader(f)]

    print(f"Evaluando {len(imagenes)} imágenes...")
    resultados = []
    for i, nombre_imagen in enumerate(imagenes, 1):
        print(f"[{i}/{len(imagenes)}] {nombre_imagen}...", end=" ")
        resultado = evaluar_imagen(nombre_imagen)
        if resultado:
            resultados.append(resultado)
            print(f"✓ F1: {resultado['f1']:.3f}")
        else:
            print("✗")

    if not resultados:
        print("❌ No se evaluó ninguna imagen correctamente.")
        return

    with open(OUTPUT_CSV, "w", newline="") as f:
        campos = [
            "nombre",
            "f1",
            "iou",
            "precision",
            "recall",
            "accuracy",
            "tp",
            "fp",
            "fn",
            "num_nucleos_gt",
            "num_nucleos_pred",
            "precision_conteo",
            "area_media_gt",
            "area_media_pred",
        ]
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resultados)

    mostrar_resumen(resultados)


def mostrar_resumen(resultados: list[dict]):
    """Imprime resumen global de las métricas."""
    f1_medio = np.mean([r["f1"] for r in resultados])
    iou_medio = np.mean([r["iou"] for r in resultados])
    precision_medio = np.mean([r["precision"] for r in resultados])
    recall_medio = np.mean([r["recall"] for r in resultados])
    accuracy_medio = np.mean([r["accuracy"] for r in resultados])
    precision_conteo_medio = np.mean([r["precision_conteo"] for r in resultados])
    area_media_gt = np.mean([r["area_media_gt"] for r in resultados])
    area_media_pred = np.mean([r["area_media_pred"] for r in resultados])

    print("\n" + "=" * 60)
    print("  EVALUACIÓN CUANTITATIVA - RESULTADOS GLOBALES")
    print("=" * 60)
    print(f"\n1. MÉTRICAS DE SEGMENTACIÓN (píxel a píxel):")
    print(f"   F1-Score:    {f1_medio*100:.2f}%  (balance precision-recall)")
    print(f"   IoU:         {iou_medio*100:.2f}%")
    print(f"   Precision:   {precision_medio*100:.2f}%")
    print(f"   Recall:      {recall_medio*100:.2f}%")
    print(f"   Accuracy:    {accuracy_medio*100:.2f}%")

    print(f"\n2. MÉTRICAS DE CONTEO (número de núcleos):")
    print(f"   Núcleos GT (media):   {np.mean([r['num_nucleos_gt'] for r in resultados]):.1f}")
    print(f"   Núcleos Pred (media): {np.mean([r['num_nucleos_pred'] for r in resultados]):.1f}")
    print(f"   Precisión conteo:     {precision_conteo_medio:.2f}%")

    print(f"\n3. MÉTRICAS DE ÁREA (px²):")
    print(f"   Área Media GT:   {area_media_gt:.2f} px²")
    print(f"   Área Media Pred: {area_media_pred:.2f} px²")
    if area_media_gt > 0:
        print(f"   Diferencia rel.: {abs(1 - area_media_pred/area_media_gt)*100:.1f}%")

    mejor = max(resultados, key=lambda x: x["f1"])
    peor = min(resultados, key=lambda x: x["f1"])
    print("\n" + "=" * 60)
    print("Mejor resultado (F1):")
    print(f"  {mejor['nombre']} -> F1 {mejor['f1']*100:.1f}% (GT:{mejor['num_nucleos_gt']} Pred:{mejor['num_nucleos_pred']})")
    print("\nPeor resultado (F1):")
    print(f"  {peor['nombre']} -> F1 {peor['f1']*100:.1f}% (GT:{peor['num_nucleos_gt']} Pred:{peor['num_nucleos_pred']})")
    print("\n" + "=" * 60)
    print(f"Evaluacion guardada en: {OUTPUT_CSV}")


if __name__ == "__main__":
    evaluar_todas_imagenes()
