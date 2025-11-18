import cv2
import numpy as np
from pathlib import Path
import xml.etree.ElementTree as ET

# Analizar una imagen representativa
img_path = "Material Celulas/H/TCGA-21-5784-01Z-00-DX1.png"
xml_path = "Material Celulas/xml/TCGA-21-5784-01Z-00-DX1.xml"

print("="*60)
print("ANÁLISIS DEL PIPELINE - DETECTANDO PROBLEMAS")
print("="*60)

# 1. CARGAR IMAGEN Y GT
img = cv2.imread(img_path)
img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# 2. ANALIZAR GT
tree = ET.parse(xml_path)
root = tree.getroot()
regions = root.findall('.//Region')

print(f"\n1. GROUND TRUTH:")
print(f"   Núcleos totales: {len(regions)}")

areas_gt = []
for region in regions:
    vertices = region.findall('.//Vertex')
    if len(vertices) < 3:
        continue
    
    points = np.array([[float(v.get('X')), float(v.get('Y'))] for v in vertices], dtype=np.int32)
    mask = np.zeros(img_gray.shape, dtype=np.uint8)
    cv2.fillPoly(mask, [points], 255)
    area = np.sum(mask > 0)
    areas_gt.append(area)

print(f"   Área media GT: {np.mean(areas_gt):.2f} px²")
print(f"   Área min GT: {np.min(areas_gt):.2f} px²")
print(f"   Área max GT: {np.max(areas_gt):.2f} px²")
print(f"   Área std GT: {np.std(areas_gt):.2f} px²")

# 3. ANALIZAR UMBRALIZACIÓN ACTUAL
print(f"\n2. UMBRALIZACIÓN ACTUAL:")

# Otsu
_, img_otsu = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
print(f"   Píxeles Otsu: {np.sum(img_otsu > 0)}")

# Local
img_local = cv2.adaptiveThreshold(
    img_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
    cv2.THRESH_BINARY_INV, 51, 2
)
print(f"   Píxeles Local: {np.sum(img_local > 0)}")

# Combinado
img_comb = cv2.bitwise_or(img_otsu, img_local)
print(f"   Píxeles Combinados: {np.sum(img_comb > 0)}")

# GT
gt_mask = np.zeros(img_gray.shape, dtype=np.uint8)
for region in regions:
    vertices = region.findall('.//Vertex')
    if len(vertices) < 3:
        continue
    points = np.array([[float(v.get('X')), float(v.get('Y'))] for v in vertices], dtype=np.int32)
    cv2.fillPoly(gt_mask, [points], 255)

print(f"   Píxeles GT: {np.sum(gt_mask > 0)}")
print(f"   Ratio Pred/GT: {np.sum(img_comb > 0) / np.sum(gt_mask > 0):.2f}x")

# 4. ANALIZAR WATERSHED
print(f"\n3. WATERSHED ACTUAL (umbral=0.3, dil=2):")

dist_transform = cv2.distanceTransform(img_comb, cv2.DIST_L2, 5)
_, sure_fg = cv2.threshold(dist_transform, 0.3 * dist_transform.max(), 255, cv2.THRESH_BINARY)
sure_fg = sure_fg.astype(np.uint8)

kernel = np.ones((3, 3), np.uint8)
sure_bg = cv2.dilate(img_comb, kernel, iterations=2)
unknown = cv2.subtract(sure_bg, sure_fg)

_, markers = cv2.connectedComponents(sure_fg)
print(f"   Semillas detectadas: {len(np.unique(markers)) - 1}")
print(f"   Píxeles sure_fg: {np.sum(sure_fg > 0)}")
print(f"   Píxeles unknown: {np.sum(unknown > 0)}")
print(f"   Ratio unknown/total: {np.sum(unknown > 0) / np.sum(img_comb > 0):.2%}")

# 5. PROBLEMAS DETECTADOS
print(f"\n4. PROBLEMAS DETECTADOS:")

# Problema 1: Sobre-detección de píxeles
over_detection = np.sum(img_comb > 0) / np.sum(gt_mask > 0)
if over_detection > 1.2:
    print(f"   ⚠️ SOBRE-DETECCIÓN: {over_detection:.2f}x más píxeles que GT")
    print(f"      → Umbralización demasiado agresiva")
    print(f"      → Solución: Ajustar C_CONSTANT o filtrar ruido")

# Problema 2: Pocas semillas
seed_ratio = (len(np.unique(markers)) - 1) / len(regions)
if seed_ratio < 0.6:
    print(f"   ⚠️ POCAS SEMILLAS: {seed_ratio:.2%} del total GT")
    print(f"      → Watershed detecta {len(np.unique(markers)) - 1} semillas vs {len(regions)} GT")
    print(f"      → Solución: Bajar UMBRAL_DISTANCIA o mejorar detección de picos")

# Problema 3: Región desconocida
unknown_ratio = np.sum(unknown > 0) / np.sum(img_comb > 0)
if unknown_ratio < 0.1:
    print(f"   ⚠️ REGIÓN DESCONOCIDA MUY PEQUEÑA: {unknown_ratio:.2%}")
    print(f"      → Watershed tiene poco margen para decidir bordes")
    print(f"      → Solución: Reducir DILATACION_BACKGROUND")

print("\n" + "="*60)
print("RECOMENDACIONES:")
print("="*60)
print("""
1. PREPROCESAMIENTO: Agregar filtrado bilateral antes de umbralizar
   → Reduce ruido sin perder bordes importantes

2. UMBRALIZACIÓN: Mejorar detección inicial
   → Probar CLAHE para mejor contraste
   → Ajustar C_CONSTANT según análisis de imagen

3. WATERSHED: Mejorar detección de semillas
   → Usar H-maxima transform para mejores picos
   → Aplicar filtro de área después de segmentar

4. POST-PROCESAMIENTO: Agregar filtrado inteligente
   → Eliminar núcleos muy grandes (fusiones)
   → Eliminar núcleos muy pequeños (ruido)
   → Validar por circularidad
""")
