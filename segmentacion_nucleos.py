import cv2
import numpy as np
import os
import csv
from pathlib import Path

# ==================== PARÁMETROS V2.0 ====================
# Umbralización
UMBRAL_ADAPTATIVO = True  # Usar Otsu automático por imagen
UMBRAL_LOCAL = True  # Umbralización local para refinamiento
BLOCK_SIZE = 51  # Tamaño de ventana para umbralización local (impar)
C_CONSTANT = 2  # Constante restada al umbral local

# Watershed
UMBRAL_DISTANCIA = 0.25  # Umbral para semillas (0.25 = más semillas)
DILATACION_BACKGROUND = 1  # Iteraciones de dilatación del fondo

# Post-procesamiento
RELLENAR_HUECOS = True  # Rellenar huecos en núcleos
CORREGIR_CONCAVIDADES = True  # Aplicar convex hull a núcleos con concavidades
SOLIDEZ_MIN = 0.78  # Umbral para detectar concavidades (basado en P5 del GT)
AREA_MIN_NUCLEO = 50  # Área mínima para filtrar ruido (mínimo del GT)

INPUT_DIR = "Material Celulas/H"
OUTPUT_DIR = "out"
GT_DIR = "Material Celulas/gt_colors"
RESULTADOS_CSV = "resultados.csv"
# ====================================================


def cargar_imagen(ruta_imagen):
    imagen_color = cv2.imread(ruta_imagen)
    imagen_gris = cv2.cvtColor(imagen_color, cv2.COLOR_BGR2GRAY)
    return imagen_color, imagen_gris


def aplicar_umbralizacion(imagen_gris):
    """
    V2.0: Umbralización secuencial (Otsu + Local adaptativo)
    
    Estrategia:
    1. Otsu global detecta regiones de núcleos
    2. Local adaptativo refina bordes DENTRO de Otsu
    3. Si AND es muy conservador, usar estrategia intermedia
    
    Mantiene el balance precision-recall evitando ruido del OR.
    """
    # 1. Otsu global: primera pasada automática
    _, imagen_otsu = cv2.threshold(
        imagen_gris, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    
    # 2. Umbralización local (si está activada)
    if not UMBRAL_LOCAL:
        return imagen_otsu, imagen_otsu, None
    
    # Local adaptativo sobre imagen original
    imagen_local = cv2.adaptiveThreshold(
        imagen_gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, BLOCK_SIZE, C_CONSTANT
    )
    
    # Estrategia secuencial: AND (solo donde ambos coinciden)
    imagen_combinada = cv2.bitwise_and(imagen_otsu, imagen_local)
    
    # Si AND pierde >40% de píxeles, usar estrategia intermedia
    pixeles_otsu = np.sum(imagen_otsu > 0)
    pixeles_and = np.sum(imagen_combinada > 0)
    
    if pixeles_and < 0.6 * pixeles_otsu:
        # Otsu + bordes de local cercanos
        kernel = np.ones((5, 5), np.uint8)
        otsu_dilatado = cv2.dilate(imagen_otsu, kernel, iterations=1)
        local_cercano = cv2.bitwise_and(imagen_local, otsu_dilatado)
        imagen_combinada = cv2.bitwise_or(imagen_otsu, local_cercano)
    
    return imagen_combinada, imagen_otsu, imagen_local


def aplicar_watershed(imagen_binaria):
    """
    Algoritmo Watershed para segmentación de núcleos
    
    V1.2: Reemplaza Region Growing por Watershed
    - Más robusto para separar núcleos tocándose
    - No requiere control manual de gradiente
    - Usa markers para guiar la inundación
    """
    # 1. TRANSFORMADA DE DISTANCIA: Encontrar centros de núcleos
    dist_transform = cv2.distanceTransform(imagen_binaria, cv2.DIST_L2, 5)
    
    # 2. SURE FOREGROUND: Centros seguros (umbral más bajo = más semillas)
    # OPTIMIZACIÓN: Umbral 0.3 en vez de 0.5 → detecta más núcleos pequeños/débiles
    _, sure_fg = cv2.threshold(
        dist_transform, UMBRAL_DISTANCIA * dist_transform.max(), 255, cv2.THRESH_BINARY
    )
    sure_fg = sure_fg.astype(np.uint8)
    
    # 3. SURE BACKGROUND: Región segura de fondo (dilatar menos = más margen)
    # OPTIMIZACIÓN: 2 iteraciones en vez de 3 → región desconocida más grande
    kernel = np.ones((3, 3), np.uint8)
    sure_bg = cv2.dilate(imagen_binaria, kernel, iterations=DILATACION_BACKGROUND)
    
    # 4. REGIÓN DESCONOCIDA: Entre foreground y background
    # Aquí es donde Watershed decide los bordes
    sure_fg_int = sure_fg.astype(np.uint8)
    unknown = cv2.subtract(sure_bg, sure_fg_int)
    
    # 5. ETIQUETAR REGIONES CONOCIDAS (semillas)
    # Cada componente conectada en sure_fg = 1 semilla
    _, markers = cv2.connectedComponents(sure_fg)
    
    # 6. MARCAR FONDO COMO 1 (no 0, que Watershed usa para desconocido)
    markers = markers + 1
    
    # 7. MARCAR REGIÓN DESCONOCIDA COMO 0
    markers[unknown == 255] = 0
    
    # 8. APLICAR WATERSHED
    # Necesita imagen en color (BGR) como referencia
    imagen_color = cv2.cvtColor(imagen_binaria, cv2.COLOR_GRAY2BGR)
    markers = cv2.watershed(imagen_color, markers)
    
    # 9. LIMPIAR MARKERS
    # Watershed marca bordes con -1, convertir fondo (1) a 0
    markers[markers == -1] = 0  # Bordes → fondo
    markers[markers == 1] = 0   # Fondo original → 0
    # Ahora: 0=fondo, 2,3,4,...=núcleos
    
    return markers


def corregir_morfologia(markers):
    """
    V2.0: Corrección morfológica SIMPLIFICADA
    
    Solo hace 2 cosas:
    1. Filtrar ruido (área < 50 px²)
    2. Corregir concavidades con convex hull (solidez < 0.78)
    
    Eliminadas las correcciones complejas:
    - Re-segmentación de elongados (CASO 2) - código complejo, pocos casos
    - Unión de fragmentos (CASO 3) - riesgo de fusiones incorrectas
    """
    if not CORREGIR_CONCAVIDADES:
        return markers
    
    markers_corregidos = markers.copy()
    ids_nucleos = np.unique(markers)
    ids_nucleos = ids_nucleos[ids_nucleos > 0]  # Excluir fondo
    
    for nucleo_id in ids_nucleos:
        # Extraer máscara del núcleo
        mascara = (markers == nucleo_id).astype(np.uint8) * 255
        
        # Encontrar contorno
        contornos, _ = cv2.findContours(
            mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        if len(contornos) == 0 or len(contornos[0]) < 5:
            continue
        
        contorno = contornos[0]
        area = cv2.contourArea(contorno)
        
        # FILTRO 1: Eliminar ruido (núcleos muy pequeños)
        if area < AREA_MIN_NUCLEO:
            markers_corregidos[mascara > 0] = 0
            continue
        
        # FILTRO 2: Corregir concavidades con convex hull
        hull = cv2.convexHull(contorno)
        area_convexa = cv2.contourArea(hull)
        
        # Calcular solidez (qué tan "lleno" está el núcleo)
        solidez = area / area_convexa if area_convexa > 0 else 1.0
        
        # Si tiene baja solidez → tiene concavidades → aplicar convex hull
        if solidez < SOLIDEZ_MIN:
            mascara_corregida = np.zeros_like(mascara)
            cv2.drawContours(mascara_corregida, [hull], -1, 255, -1)
            markers_corregidos[mascara_corregida > 0] = nucleo_id
    
    return markers_corregidos


def rellenar_huecos_nucleos(markers):
    """
    V2.0: Rellena huecos de cada núcleo DESPUÉS de Watershed
    
    Seguro porque cada núcleo ya tiene su propio ID.
    Rellena el contorno completo para evitar huecos internos.
    """
    if not RELLENAR_HUECOS:
        return markers
    
    markers_rellenos = markers.copy()
    
    # Obtener IDs únicos de núcleos
    ids_nucleos = np.unique(markers)
    ids_nucleos = ids_nucleos[ids_nucleos > 0]  # Excluir fondo (0)
    
    for nucleo_id in ids_nucleos:
        # Extraer máscara del núcleo individual
        mascara_nucleo = (markers == nucleo_id).astype(np.uint8) * 255
        
        # Encontrar contornos del núcleo
        contornos, _ = cv2.findContours(
            mascara_nucleo, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        if len(contornos) == 0:
            continue
        
        # Crear máscara rellena: dibujar contorno FILLED
        mascara_rellena = np.zeros_like(mascara_nucleo)
        cv2.drawContours(mascara_rellena, contornos, -1, 255, thickness=cv2.FILLED)
        
        # Actualizar markers: donde está relleno, poner ID del núcleo
        markers_rellenos[mascara_rellena > 0] = nucleo_id
    
    return markers_rellenos


def crear_imagen_segmentada(markers, imagen_original):
    # COLOREADA: Asignar color aleatorio a cada núcleo
    imagen_coloreada = np.zeros_like(imagen_original)
    ids_nucleos = np.unique(markers)
    ids_nucleos = ids_nucleos[ids_nucleos > 1]

    np.random.seed(42)
    for nucleo_id in ids_nucleos:
        color = np.random.randint(0, 255, 3).tolist()
        imagen_coloreada[markers == nucleo_id] = color

    return imagen_coloreada


def guardar_resultados(
    nombre_imagen,
    imagen_original,
    imagen_gris,
    imagen_otsu,
    imagen_local,
    imagen_coloreada,
    num_nucleos,
):
    base_name = os.path.splitext(nombre_imagen)[0]
    carpeta_imagen = f"{OUTPUT_DIR}/{base_name}"
    Path(carpeta_imagen).mkdir(parents=True, exist_ok=True)

    # GUARDAR: Imágenes individuales del pipeline
    cv2.imwrite(f"{carpeta_imagen}/1_BN.png", imagen_gris)
    cv2.imwrite(f"{carpeta_imagen}/2_umbral_otsu.png", imagen_otsu)
    
    if imagen_local is not None:
        cv2.imwrite(f"{carpeta_imagen}/3_umbral_local.png", imagen_local)
    
    cv2.imwrite(f"{carpeta_imagen}/4_coloreada.png", imagen_coloreada)

    # DIFERENCIAS: Comparar con ground truth
    ruta_gt = Path(GT_DIR) / nombre_imagen
    img_diff = None
    img_gt = None

    if ruta_gt.exists():
        img_gt = cv2.imread(str(ruta_gt))
        if img_gt is not None:
            cv2.imwrite(f"{carpeta_imagen}/5_GT.png", img_gt)

            # Máscaras binarias
            img_gt_gray = cv2.cvtColor(img_gt, cv2.COLOR_BGR2GRAY)
            _, mask_gt = cv2.threshold(img_gt_gray, 10, 255, cv2.THRESH_BINARY)

            img_coloreada_gray = cv2.cvtColor(imagen_coloreada, cv2.COLOR_BGR2GRAY)
            _, mask_pred = cv2.threshold(img_coloreada_gray, 10, 255, cv2.THRESH_BINARY)

            # Imagen de diferencias: ROJO=falsos negativos, VERDE=correctos, AZUL=falsos positivos
            img_diff = np.zeros_like(img_gt)
            falsos_negativos = cv2.bitwise_and(mask_gt, cv2.bitwise_not(mask_pred))
            img_diff[falsos_negativos > 0] = [0, 0, 255]

            verdaderos_positivos = cv2.bitwise_and(mask_gt, mask_pred)
            img_diff[verdaderos_positivos > 0] = [0, 255, 0]

            falsos_positivos = cv2.bitwise_and(mask_pred, cv2.bitwise_not(mask_gt))
            img_diff[falsos_positivos > 0] = [255, 0, 0]

            cv2.imwrite(f"{carpeta_imagen}/6_diferencias.png", img_diff)

    # COMPARATIVA: Grid 2x3 con todas las etapas
    img_gris_bgr = cv2.cvtColor(imagen_gris, cv2.COLOR_GRAY2BGR)
    img_otsu_bgr = cv2.cvtColor(imagen_otsu, cv2.COLOR_GRAY2BGR)
    
    if imagen_local is not None:
        img_local_bgr = cv2.cvtColor(imagen_local, cv2.COLOR_GRAY2BGR)
    else:
        img_local_bgr = np.zeros_like(img_otsu_bgr)

    h, w = imagen_original.shape[:2]
    scale = 0.4
    new_size = (int(w * scale), int(h * scale))

    img_gris_small = cv2.resize(img_gris_bgr, new_size)
    img_otsu_small = cv2.resize(img_otsu_bgr, new_size)
    img_local_small = cv2.resize(img_local_bgr, new_size)
    img_coloreada_small = cv2.resize(imagen_coloreada, new_size)

    if img_gt is not None:
        img_gt_small = cv2.resize(img_gt, new_size)
    else:
        img_gt_small = np.zeros_like(img_coloreada_small)

    if img_diff is not None:
        img_diff_small = cv2.resize(img_diff, new_size)
    else:
        img_diff_small = np.zeros_like(img_coloreada_small)

    fila1 = np.hstack([img_gris_small, img_otsu_small, img_local_small])
    fila2 = np.hstack([img_coloreada_small, img_gt_small, img_diff_small])
    comparativa = np.vstack([fila1, fila2])

    cv2.imwrite(f"{carpeta_imagen}/comparativa.png", comparativa)


def procesar_imagen(ruta_imagen):
    nombre_imagen = os.path.basename(ruta_imagen)

    # PIPELINE V2.0 - SIMPLIFICADO
    imagen_original, imagen_gris = cargar_imagen(ruta_imagen)
    imagen_combinada, imagen_otsu, imagen_local = aplicar_umbralizacion(imagen_gris)
    
    # Watershed: Separar núcleos tocándose
    markers = aplicar_watershed(imagen_combinada)
    
    # Post-procesamiento:
    # 1. Rellenar huecos internos
    markers = rellenar_huecos_nucleos(markers)
    
    # 2. Corregir concavidades y filtrar ruido
    markers = corregir_morfologia(markers)

    # Calcular núcleos
    ids_nucleos = np.unique(markers)
    ids_nucleos = ids_nucleos[ids_nucleos > 0]  # Excluir fondo
    num_nucleos = len(ids_nucleos)

    areas = []
    for nucleo_id in ids_nucleos:
        area = np.sum(markers == nucleo_id)
        areas.append(area)

    area_media = np.mean(areas) if areas else 0
    imagen_coloreada = crear_imagen_segmentada(markers, imagen_original)

    guardar_resultados(
        nombre_imagen,
        imagen_original,
        imagen_gris,
        imagen_otsu,
        imagen_local,
        imagen_coloreada,
        num_nucleos,
    )

    return nombre_imagen, num_nucleos, area_media, areas


def guardar_csv(resultados):
    with open(RESULTADOS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["Imagen", "Num_Nucleos", "Area_Media_px2", "Area_Min_px2", "Area_Max_px2"]
        )

        for resultado in resultados:
            areas = resultado["areas_individuales"]
            area_min = min(areas) if areas else 0
            area_max = max(areas) if areas else 0

            writer.writerow(
                [
                    resultado["nombre"],
                    resultado["num_nucleos"],
                    f"{resultado['area_media']:.2f}",
                    area_min,
                    area_max,
                ]
            )


def procesar_todas_imagenes():
    imagenes = (
        list(Path(INPUT_DIR).glob("*.png"))
        + list(Path(INPUT_DIR).glob("*.jpg"))
        + list(Path(INPUT_DIR).glob("*.tif"))
    )

    if not imagenes:
        print(f"No se encontraron imagenes en {INPUT_DIR}")
        return

    print(f"Procesando {len(imagenes)} imagenes...")
    resultados = []

    for i, ruta_imagen in enumerate(imagenes, 1):
        print(f"[{i}/{len(imagenes)}]", end=" ", flush=True)
        try:
            nombre, num_nucleos, area_media, areas = procesar_imagen(str(ruta_imagen))
            resultados.append(
                {
                    "nombre": nombre,
                    "num_nucleos": num_nucleos,
                    "area_media": area_media,
                    "areas_individuales": areas,
                }
            )
        except Exception as e:
            print(f"Error: {e}")

    guardar_csv(resultados)
    print(f"\nCompletado. Resultados en: {RESULTADOS_CSV}")


def main():
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    print(f"Directorio de salida: {OUTPUT_DIR}")
    procesar_todas_imagenes()


if __name__ == "__main__":
    main()
