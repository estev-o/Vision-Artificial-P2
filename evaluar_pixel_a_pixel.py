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
OUTPUT_CSV = "evaluacion.csv"  # Nombre unificado
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


def binarizar_imagen(imagen):
    """Convierte imagen coloreada a binaria (blanco=núcleo, negro=fondo)"""
    if len(imagen.shape) == 3:
        gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    else:
        gray = imagen
    
    _, binaria = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    return binaria


def calcular_metricas_pixel(pred_binaria, gt_binaria):
    """
    Calcula métricas píxel a píxel (F1-Score, IoU, Precision, Recall)
    
    pred_binaria: máscara predicha (255=núcleo, 0=fondo)
    gt_binaria: máscara ground truth (255=núcleo, 0=fondo)
    
    Nota: F1-Score y Dice son matemáticamente equivalentes:
          F1 = 2×(Precision×Recall)/(Precision+Recall) = 2×TP/(2×TP+FP+FN) = Dice
    """
    # Convertir a booleano
    pred = (pred_binaria > 0).astype(np.uint8)
    gt = (gt_binaria > 0).astype(np.uint8)
    
    # True Positives: píxeles correctamente clasificados como núcleo
    tp = np.sum((pred == 1) & (gt == 1))
    
    # False Positives: píxeles clasificados como núcleo pero son fondo
    fp = np.sum((pred == 1) & (gt == 0))
    
    # False Negatives: píxeles que son núcleo pero clasificados como fondo
    fn = np.sum((pred == 0) & (gt == 1))
    
    # True Negatives: píxeles correctamente clasificados como fondo
    tn = np.sum((pred == 0) & (gt == 0))
    
    # Evitar división por cero
    if tp + fp == 0:
        precision = 0.0
    else:
        precision = tp / (tp + fp)
    
    if tp + fn == 0:
        recall = 0.0
    else:
        recall = tp / (tp + fn)
    
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * (precision * recall) / (precision + recall)
    
    if tp + fp + fn == 0:
        iou = 0.0
    else:
        iou = tp / (tp + fp + fn)
    
    # Accuracy global
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0.0
    
    return {
        'f1': f1,
        'iou': iou,
        'precision': precision,
        'recall': recall,
        'accuracy': accuracy,
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'tn': tn
    }


def evaluar_imagen(nombre_imagen):
    """Evalúa una imagen comparando predicción vs ground truth píxel a píxel"""
    nombre_base = Path(nombre_imagen).stem
    
    # Cargar predicción (coloreada)
    ruta_pred = Path(OUTPUT_DIR) / nombre_base / "4_coloreada.png"
    if not ruta_pred.exists():
        print(f"⚠️  No existe predicción para {nombre_imagen}")
        return None
    
    pred_color = cv2.imread(str(ruta_pred))
    pred_binaria = binarizar_imagen(pred_color)
    
    # Cargar ground truth (coloreada)
    ruta_gt = Path(GT_COLORS_DIR) / nombre_imagen
    if not ruta_gt.exists():
        print(f"⚠️  No existe GT para {nombre_imagen}")
        return None
    
    gt_color = cv2.imread(str(ruta_gt))
    gt_binaria = binarizar_imagen(gt_color)
    
    # Asegurar que ambas tienen el mismo tamaño
    if pred_binaria.shape != gt_binaria.shape:
        print(f"⚠️  Tamaños diferentes: pred {pred_binaria.shape} vs gt {gt_binaria.shape}")
        # Redimensionar predicción al tamaño del GT
        pred_binaria = cv2.resize(pred_binaria, (gt_binaria.shape[1], gt_binaria.shape[0]))
    
    # Calcular métricas píxel a píxel
    metricas = calcular_metricas_pixel(pred_binaria, gt_binaria)
    
    # Cargar conteo desde XML
    ruta_xml = Path(XML_DIR) / f"{nombre_base}.xml"
    num_nucleos_gt, areas_gt = cargar_ground_truth_xml(ruta_xml)
    
    # Contar núcleos en predicción
    num_labels, labels = cv2.connectedComponents(pred_binaria)
    num_nucleos_pred = num_labels - 1  # Restar el fondo
    
    # Calcular áreas
    area_total_gt = areas_gt if areas_gt else [np.sum(gt_binaria > 0)]
    area_media_gt = np.mean(area_total_gt) if area_total_gt else 0
    area_media_pred = np.sum(pred_binaria > 0) / num_nucleos_pred if num_nucleos_pred > 0 else 0
    
    # Error de conteo
    error_conteo_abs = abs(num_nucleos_pred - num_nucleos_gt)
    precision_conteo = 100 - (error_conteo_abs / num_nucleos_gt * 100) if num_nucleos_gt > 0 else 0
    
    return {
        'nombre': nombre_imagen,
        'f1': metricas['f1'],
        'iou': metricas['iou'],
        'precision': metricas['precision'],
        'recall': metricas['recall'],
        'accuracy': metricas['accuracy'],
        'tp': metricas['tp'],
        'fp': metricas['fp'],
        'fn': metricas['fn'],
        'num_nucleos_gt': num_nucleos_gt,
        'num_nucleos_pred': num_nucleos_pred,
        'precision_conteo': precision_conteo,
        'area_media_gt': area_media_gt,
        'area_media_pred': area_media_pred
    }


def evaluar_todas_imagenes():
    """Evalúa todas las imágenes y genera CSV con resultados"""
    resultados = []
    
    # Obtener lista de imágenes del CSV de resultados
    if not Path(RESULTADOS_CSV).exists():
        print(f"❌ No existe {RESULTADOS_CSV}. Ejecuta primero la segmentación.")
        return
    
    with open(RESULTADOS_CSV, 'r') as f:
        reader = csv.DictReader(f)
        imagenes = [row['Imagen'] for row in reader]
    
    print(f"Evaluando {len(imagenes)} imágenes...")
    
    for i, nombre_imagen in enumerate(imagenes, 1):
        print(f"[{i}/{len(imagenes)}] {nombre_imagen}...", end=" ")
        resultado = evaluar_imagen(nombre_imagen)
        if resultado:
            resultados.append(resultado)
            print(f"✓ F1: {resultado['f1']:.3f}")
        else:
            print("✗")
    
    # Guardar resultados en CSV
    if resultados:
        with open(OUTPUT_CSV, 'w', newline='') as f:
            campos = ['nombre', 'f1', 'iou', 'precision', 'recall', 
                     'accuracy', 'tp', 'fp', 'fn', 'num_nucleos_gt', 'num_nucleos_pred', 
                     'precision_conteo', 'area_media_gt', 'area_media_pred']
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(resultados)
        
        # Mostrar resumen
        mostrar_resumen(resultados)
    else:
        print("❌ No se evaluó ninguna imagen correctamente.")


def mostrar_resumen(resultados):
    """Muestra resumen de resultados en consola"""
    f1_medio = np.mean([r['f1'] for r in resultados])
    iou_medio = np.mean([r['iou'] for r in resultados])
    precision_medio = np.mean([r['precision'] for r in resultados])
    recall_medio = np.mean([r['recall'] for r in resultados])
    accuracy_medio = np.mean([r['accuracy'] for r in resultados])
    precision_conteo_medio = np.mean([r['precision_conteo'] for r in resultados])
    
    print("\n" + "="*60)
    print("  EVALUACION PIXEL A PIXEL - RESULTADOS GLOBALES")
    print("="*60)
    print(f"\n1. SEGMENTACION (píxel a píxel):")
    print(f"   F1-Score:    {f1_medio*100:.2f}%  (balance precision-recall)")
    print(f"   IoU:         {iou_medio*100:.2f}%  (Intersection over Union)")
    print(f"   Precision:   {precision_medio*100:.2f}%  (de los píxeles detectados, cuántos correctos)")
    print(f"   Recall:      {recall_medio*100:.2f}%  (de los píxeles reales, cuántos detectados)")
    print(f"   Accuracy:    {accuracy_medio*100:.2f}%  (píxeles correctos global)")
    
    print(f"\n2. CONTEO:")
    print(f"   Precision:   {precision_conteo_medio:.2f}%")
    
    # Distribución F1
    excelente = sum(1 for r in resultados if r['f1'] >= 0.9)
    bueno = sum(1 for r in resultados if 0.7 <= r['f1'] < 0.9)
    regular = sum(1 for r in resultados if 0.5 <= r['f1'] < 0.7)
    malo = sum(1 for r in resultados if r['f1'] < 0.5)
    
    print("\n" + "="*60)
    print("Distribución F1-Score:")
    print(f"  Excelente (>=90%):  {excelente} imagenes")
    print(f"  Bueno (70-90%):     {bueno} imagenes")
    print(f"  Regular (50-70%):   {regular} imagenes")
    print(f"  Malo (<50%):        {malo} imagenes")
    
    # Mejor y peor
    mejor = max(resultados, key=lambda x: x['f1'])
    peor = min(resultados, key=lambda x: x['f1'])
    
    print("\n" + "="*60)
    print(f"Mejor resultado (F1):")
    print(f"  {mejor['nombre']}")
    print(f"  F1: {mejor['f1']*100:.1f}% (GT:{mejor['num_nucleos_gt']} Pred:{mejor['num_nucleos_pred']})")
    
    print(f"\nPeor resultado (F1):")
    print(f"  {peor['nombre']}")
    print(f"  F1: {peor['f1']*100:.1f}% (GT:{peor['num_nucleos_gt']} Pred:{peor['num_nucleos_pred']})")
    
    print("\n" + "="*60)
    print(f"Evaluacion guardada en: {OUTPUT_CSV}")


if __name__ == "__main__":
    evaluar_todas_imagenes()
