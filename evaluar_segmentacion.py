import cv2
import numpy as np
import csv
from pathlib import Path
import xml.etree.ElementTree as ET

# ==================== PARÁMETROS ====================
XML_DIR = "Material Celulas/xml"
GT_COLORS_DIR = "Material Celulas/gt_colors"
OUTPUT_DIR = "out"
RESULTADOS_CSV = "resultados.csv"
OUTPUT_CSV = "evaluacion.csv"
IOU_THRESHOLD = 0.5  # Umbral para considerar un núcleo como TP
# ====================================================


def cargar_ground_truth_xml(ruta_xml):
    """Carga información de núcleos desde XML"""
    if not Path(ruta_xml).exists():
        return 0, []

    try:
        tree = ET.parse(ruta_xml)
        root = tree.getroot()
        regiones = root.findall(".//Region")

        areas_gt = []
        for region in regiones:
            area_str = region.get("Area")
            if area_str:
                areas_gt.append(float(area_str))

        return len(areas_gt), areas_gt

    except Exception as e:
        print(f"Error al leer XML {ruta_xml}: {e}")
        return 0, []


def extraer_mascaras_individuales(imagen_coloreada):
    """Extrae máscara binaria de cada núcleo individual desde imagen coloreada"""
    mascaras = []
    areas = []

    # Convertir a escala de grises para detectar regiones
    if len(imagen_coloreada.shape) == 3:
        gray = cv2.cvtColor(imagen_coloreada, cv2.COLOR_BGR2GRAY)
    else:
        gray = imagen_coloreada

    # Binarizar
    _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)

    # Encontrar componentes conectadas (cada núcleo)
    num_labels, labels = cv2.connectedComponents(binary)

    # Extraer máscara de cada núcleo (excluir fondo=0)
    for label_id in range(1, num_labels):
        mascara = (labels == label_id).astype(np.uint8) * 255
        area = np.sum(mascara > 0)
        mascaras.append(mascara)
        areas.append(area)

    return mascaras, areas


def calcular_iou(mascara1, mascara2):
    """Calcula Intersection over Union entre dos máscaras binarias"""
    interseccion = np.logical_and(mascara1, mascara2).astype(np.uint8)
    union = np.logical_or(mascara1, mascara2).astype(np.uint8)

    area_interseccion = np.sum(interseccion)
    area_union = np.sum(union)

    if area_union == 0:
        return 0.0

    return area_interseccion / area_union


def matching_nucleos_iou(mascaras_gt, mascaras_pred, areas_gt, areas_pred):
    """
    Hace matching entre núcleos GT y predichos usando IoU.
    OPTIMIZADO: Solo calcula IoU si hay overlap espacial (bounding boxes)
    """
    n_gt = len(mascaras_gt)
    n_pred = len(mascaras_pred)

    if n_gt == 0 and n_pred == 0:
        return 0, 0, 0, [], [], []

    if n_gt == 0:
        return 0, n_pred, 0, [], [], []

    if n_pred == 0:
        return 0, 0, n_gt, [], [], []

    # OPTIMIZACIÓN: Precalcular bounding boxes para filtrado rápido
    def get_bbox(mask):
        coords = np.argwhere(mask > 0)
        if len(coords) == 0:
            return None
        y_min, x_min = coords.min(axis=0)
        y_max, x_max = coords.max(axis=0)
        return (y_min, y_max, x_min, x_max)

    def boxes_overlap(box1, box2):
        if box1 is None or box2 is None:
            return False
        y1_min, y1_max, x1_min, x1_max = box1
        y2_min, y2_max, x2_min, x2_max = box2
        return not (
            x1_max < x2_min or x2_max < x1_min or y1_max < y2_min or y2_max < y1_min
        )

    bboxes_gt = [get_bbox(m) for m in mascaras_gt]
    bboxes_pred = [get_bbox(m) for m in mascaras_pred]

    # Solo calcular IoU si bounding boxes se solapan
    candidatos = []  # (iou, idx_gt, idx_pred)

    for i in range(n_gt):
        for j in range(n_pred):
            # Filtro rápido: solo si boxes se solapan
            if boxes_overlap(bboxes_gt[i], bboxes_pred[j]):
                iou = calcular_iou(mascaras_gt[i], mascaras_pred[j])
                if iou >= IOU_THRESHOLD:
                    candidatos.append((iou, i, j))

    # Ordenar por IoU descendente
    candidatos.sort(reverse=True)

    # Matching voraz
    gt_asignados = set()
    pred_asignados = set()
    matches = []
    ious_tp = []
    errores_area = []

    for iou, idx_gt, idx_pred in candidatos:
        if idx_gt in gt_asignados or idx_pred in pred_asignados:
            continue

        # TRUE POSITIVE
        gt_asignados.add(idx_gt)
        pred_asignados.add(idx_pred)
        matches.append((idx_gt, idx_pred, iou, areas_gt[idx_gt], areas_pred[idx_pred]))
        ious_tp.append(iou)

        # Error de área individual
        error_area_rel = (
            abs(areas_pred[idx_pred] - areas_gt[idx_gt]) / areas_gt[idx_gt] * 100
        )
        errores_area.append(error_area_rel)

    TP = len(matches)
    FP = n_pred - len(pred_asignados)
    FN = n_gt - len(gt_asignados)

    return TP, FP, FN, matches, ious_tp, errores_area


def evaluar_imagen(nombre_imagen, num_nucleos_pred, area_media_pred):
    """Evaluación completa con matching IoU núcleo por núcleo"""
    base_name = nombre_imagen.replace(".png", "")

    # CARGAR GT desde XML
    ruta_xml = Path(XML_DIR) / f"{base_name}.xml"
    if not ruta_xml.exists():
        return None

    num_nucleos_gt, areas_gt = cargar_ground_truth_xml(str(ruta_xml))
    if num_nucleos_gt == 0:
        return None

    # CARGAR máscaras GT y predichas
    ruta_gt_img = Path(GT_COLORS_DIR) / nombre_imagen
    ruta_pred_img = Path(OUTPUT_DIR) / base_name / "4_coloreada.png"

    if not ruta_gt_img.exists() or not ruta_pred_img.exists():
        print(f"Advertencia: No se encontraron imágenes para {nombre_imagen}")
        return None

    img_gt = cv2.imread(str(ruta_gt_img))
    img_pred = cv2.imread(str(ruta_pred_img))

    # Extraer máscaras individuales
    mascaras_gt, areas_gt_img = extraer_mascaras_individuales(img_gt)
    mascaras_pred, areas_pred_img = extraer_mascaras_individuales(img_pred)

    # Usar áreas del XML si están disponibles, si no usar las de la imagen
    if len(areas_gt) == len(mascaras_gt):
        areas_gt_final = areas_gt
    else:
        areas_gt_final = areas_gt_img

    # MATCHING con IoU
    TP, FP, FN, matches, ious_tp, errores_area_individual = matching_nucleos_iou(
        mascaras_gt, mascaras_pred, areas_gt_final, areas_pred_img
    )

    # MÉTRICAS DE SEGMENTACIÓN
    precision_seg = (TP / (TP + FP) * 100) if (TP + FP) > 0 else 0
    recall_seg = (TP / (TP + FN) * 100) if (TP + FN) > 0 else 0
    f1_score = (
        (2 * precision_seg * recall_seg / (precision_seg + recall_seg))
        if (precision_seg + recall_seg) > 0
        else 0
    )

    iou_medio = np.mean(ious_tp) if ious_tp else 0

    # MÉTRICAS DE CONTEO
    error_conteo = abs(num_nucleos_pred - num_nucleos_gt)
    error_relativo_conteo = (error_conteo / num_nucleos_gt) * 100
    precision_conteo = max(0, 100 - error_relativo_conteo)

    # MÉTRICAS DE ÁREA
    area_media_gt = np.mean(areas_gt_final) if areas_gt_final else 0

    # Error de área global (media)
    error_area_media = abs(area_media_pred - area_media_gt)
    error_relativo_area_media = (
        (error_area_media / area_media_gt) * 100 if area_media_gt > 0 else 0
    )
    precision_area_media = max(0, 100 - error_relativo_area_media)

    # Error de área individual (solo TPs)
    error_area_individual_medio = (
        np.mean(errores_area_individual) if errores_area_individual else 0
    )
    precision_area_individual = max(0, 100 - error_area_individual_medio)

    return {
        "nombre": nombre_imagen,
        # Segmentación
        "TP": TP,
        "FP": FP,
        "FN": FN,
        "precision_seg": precision_seg,
        "recall_seg": recall_seg,
        "f1_score": f1_score,
        "iou_medio": iou_medio,
        # Conteo
        "nucleos_gt": num_nucleos_gt,
        "nucleos_pred": num_nucleos_pred,
        "error_conteo": error_conteo,
        "precision_conteo": precision_conteo,
        # Área
        "area_media_gt": area_media_gt,
        "area_media_pred": area_media_pred,
        "precision_area_media": precision_area_media,
        "precision_area_individual": precision_area_individual,
    }


def evaluar_todas():
    # LEER resultados de segmentación
    try:
        with open(RESULTADOS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            resultados = list(reader)
    except FileNotFoundError:
        print(f"Error: No se encontro {RESULTADOS_CSV}")
        print(f"Ejecuta primero segmentacion_nucleos.py")
        return

    # EVALUAR cada imagen
    evaluaciones = []
    for i, resultado in enumerate(resultados, 1):
        print(f"[{i}/{len(resultados)}]", end=" ", flush=True)

        nombre = resultado["Imagen"]
        num_nucleos_pred = int(resultado["Num_Nucleos"])
        area_media_pred = float(resultado["Area_Media_px2"])

        metricas = evaluar_imagen(nombre, num_nucleos_pred, area_media_pred)
        if metricas:
            evaluaciones.append(metricas)

    if not evaluaciones:
        print(f"\nNo se pudo evaluar ninguna imagen.")
        return

    # CALCULAR métricas globales
    # 1. Segmentación (IoU-based)
    precision_seg_global = np.mean([e["precision_seg"] for e in evaluaciones])
    recall_seg_global = np.mean([e["recall_seg"] for e in evaluaciones])
    f1_global = np.mean([e["f1_score"] for e in evaluaciones])
    iou_medio_global = np.mean([e["iou_medio"] for e in evaluaciones])

    # 2. Conteo
    precision_conteo_global = np.mean([e["precision_conteo"] for e in evaluaciones])

    # 3. Área
    precision_area_media_global = np.mean(
        [e["precision_area_media"] for e in evaluaciones]
    )
    precision_area_individual_global = np.mean(
        [e["precision_area_individual"] for e in evaluaciones]
    )

    # DISTRIBUCIÓN por rangos (F1-Score para segmentación)
    excelente_seg = sum(1 for e in evaluaciones if e["f1_score"] >= 90)
    bueno_seg = sum(1 for e in evaluaciones if 70 <= e["f1_score"] < 90)
    regular_seg = sum(1 for e in evaluaciones if 50 <= e["f1_score"] < 70)
    malo_seg = sum(1 for e in evaluaciones if e["f1_score"] < 50)

    # DISTRIBUCIÓN conteo
    excelente_conteo = sum(1 for e in evaluaciones if e["precision_conteo"] >= 90)
    bueno_conteo = sum(1 for e in evaluaciones if 70 <= e["precision_conteo"] < 90)
    regular_conteo = sum(1 for e in evaluaciones if 50 <= e["precision_conteo"] < 70)
    malo_conteo = sum(1 for e in evaluaciones if e["precision_conteo"] < 50)

    # GUARDAR CSV de evaluación ampliado
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Imagen",
                "TP",
                "FP",
                "FN",
                "Precision_Seg_%",
                "Recall_Seg_%",
                "F1-Score_%",
                "IoU_Medio",
                "Nucleos_GT",
                "Nucleos_Pred",
                "Precision_Conteo_%",
                "Area_GT",
                "Area_Pred",
                "Precision_Area_Media_%",
                "Precision_Area_Individual_%",
            ]
        )

        for ev in evaluaciones:
            writer.writerow(
                [
                    ev["nombre"],
                    ev["TP"],
                    ev["FP"],
                    ev["FN"],
                    f"{ev['precision_seg']:.2f}",
                    f"{ev['recall_seg']:.2f}",
                    f"{ev['f1_score']:.2f}",
                    f"{ev['iou_medio']:.3f}",
                    ev["nucleos_gt"],
                    ev["nucleos_pred"],
                    f"{ev['precision_conteo']:.2f}",
                    f"{ev['area_media_gt']:.2f}",
                    f"{ev['area_media_pred']:.2f}",
                    f"{ev['precision_area_media']:.2f}",
                    f"{ev['precision_area_individual']:.2f}",
                ]
            )

    # MEJORES Y PEORES resultados
    mejor_seg = max(evaluaciones, key=lambda x: x["f1_score"])
    peor_seg = min(evaluaciones, key=lambda x: x["f1_score"])
    mejor_conteo = max(evaluaciones, key=lambda x: x["precision_conteo"])
    peor_conteo = min(evaluaciones, key=lambda x: x["precision_conteo"])
    mejor_area = max(evaluaciones, key=lambda x: x["precision_area_individual"])
    peor_area = min(evaluaciones, key=lambda x: x["precision_area_individual"])

    # MOSTRAR resumen
    print(f"\n")
    print(f"{'='*60}")
    print(f"  EVALUACION CUANTITATIVA - RESULTADOS GLOBALES")
    print(f"{'='*60}\n")

    print(f"1. SEGMENTACION (matching IoU >= {IOU_THRESHOLD}):")
    print(
        f"   Precision: {precision_seg_global:.2f}%  (de los detectados, cuantos son correctos)"
    )
    print(
        f"   Recall:    {recall_seg_global:.2f}%  (de los reales, cuantos se detectan)"
    )
    print(f"   F1-Score:  {f1_global:.2f}%")
    print(f"   IoU medio: {iou_medio_global:.3f}")

    print(f"\n2. CONTEO:")
    print(f"   Precision: {precision_conteo_global:.2f}%")

    print(f"\n3. MEDICION DE AREAS:")
    print(f"   Precision area media:      {precision_area_media_global:.2f}%")
    print(
        f"   Precision area individual: {precision_area_individual_global:.2f}%  (solo TPs)"
    )

    print(f"\n{'='*60}")
    print(f"Distribucion de precision (SEGMENTACION - F1):")
    print(f"  Excelente (>=90%):  {excelente_seg} imagenes")
    print(f"  Bueno (70-90%):     {bueno_seg} imagenes")
    print(f"  Regular (50-70%):   {regular_seg} imagenes")
    print(f"  Malo (<50%):        {malo_seg} imagenes")

    print(f"\nDistribucion de precision (CONTEO):")
    print(f"  Excelente (>=90%):  {excelente_conteo} imagenes")
    print(f"  Bueno (70-90%):     {bueno_conteo} imagenes")
    print(f"  Regular (50-70%):   {regular_conteo} imagenes")
    print(f"  Malo (<50%):        {malo_conteo} imagenes")

    print(f"\n{'='*60}")
    print(f"Mejor resultado (SEGMENTACION):")
    print(f"  {mejor_seg['nombre']}")
    print(
        f"  F1: {mejor_seg['f1_score']:.1f}% (TP:{mejor_seg['TP']} FP:{mejor_seg['FP']} FN:{mejor_seg['FN']})"
    )

    print(f"\nPeor resultado (SEGMENTACION):")
    print(f"  {peor_seg['nombre']}")
    print(
        f"  F1: {peor_seg['f1_score']:.1f}% (TP:{peor_seg['TP']} FP:{peor_seg['FP']} FN:{peor_seg['FN']})"
    )

    print(f"\nMejor resultado (CONTEO):")
    print(f"  {mejor_conteo['nombre']}")
    print(
        f"  {mejor_conteo['precision_conteo']:.1f}% (GT:{mejor_conteo['nucleos_gt']} Pred:{mejor_conteo['nucleos_pred']})"
    )

    print(f"\nPeor resultado (CONTEO):")
    print(f"  {peor_conteo['nombre']}")
    print(
        f"  {peor_conteo['precision_conteo']:.1f}% (GT:{peor_conteo['nucleos_gt']} Pred:{peor_conteo['nucleos_pred']})"
    )

    print(f"\nMejor resultado (AREA individual):")
    print(f"  {mejor_area['nombre']}")
    print(
        f"  {mejor_area['precision_area_individual']:.1f}% (GT:{mejor_area['area_media_gt']:.1f} Pred:{mejor_area['area_media_pred']:.1f})"
    )

    print(f"\nPeor resultado (AREA individual):")
    print(f"  {peor_area['nombre']}")
    print(
        f"  {peor_area['precision_area_individual']:.1f}% (GT:{peor_area['area_media_gt']:.1f} Pred:{peor_area['area_media_pred']:.1f})"
    )

    print(f"\n{'='*60}")
    print(f"Evaluacion guardada en: {OUTPUT_CSV}\n")


def main():
    evaluar_todas()


if __name__ == "__main__":
    main()
