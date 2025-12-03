import cv2
import numpy as np
import os
import csv
from pathlib import Path
from scipy import ndimage
from scipy.signal import find_peaks
from skimage import filters, morphology, segmentation, feature, util, measure

# ========================= Parámetros Globales ==============================
MIN_DISTANCE = 5  # Distancia mínima entre picos (evita sobre-segmentación)
AREA_MIN_NUCLEO = 50  # Filtro de ruido (P5 del GT = 80 px², usamos 50 para recall)

# Umbralización adaptativa por modas (V3.3)
DETECTAR_MODAS = True  # Decide entre Otsu y Multi-Otsu según número de modas
PROMINENCIA_MODAS = 0.001  # Sensibilidad para detectar picos en histograma
DISTANCIA_MODAS = 5  # Separación mínima entre picos
SIGMA_HIST = 1.5  # Suavizado del histograma antes de buscar modas

# Post-procesamiento V3.1 (unión inteligente de fragmentos)
THRESHOLD_CONTACTO = 0.2  # Si contacto > 20% del perímetro menor → fusionar (más agresivo)
USAR_UNION_FRAGMENTOS = True  # Activar/desactivar unión post-watershed

# Post-procesamiento V3.1 (relleno de contorno robusto)
USAR_RELLENO_CONTORNO = True  # Rellenar núcleos por contorno (más robusto que remove_small_holes)

# Directorios
INPUT_DIR = "Material Celulas/H"
OUTPUT_DIR = "visualizaciones"
GT_DIR = "Material Celulas/gt_colors"
RESULTADOS_CSV = "resultados.csv"
# ============================================================================

# Parámetros de suavizado
DIST_SMOOTH_SIGMA = 1.2  # sigma para gaussian smoothing del mapa de distancia
# ---------------------------------------------------------------------------


def cargar_imagen(ruta_imagen):
    imagen_color = cv2.imread(ruta_imagen)
    if imagen_color is None:
        raise FileNotFoundError(f"No se pudo leer la imagen: {ruta_imagen}")
    imagen_gris = cv2.cvtColor(imagen_color, cv2.COLOR_BGR2GRAY)
    return imagen_color, imagen_gris





def detectar_modas_hist(imagen_gris):
    """
    Detecta el número de modas del histograma y decide el umbral:
    - 2 modas → Otsu
    - ≥3 modas → Multi-Otsu (toma la clase más oscura)
    """
    if not DETECTAR_MODAS:
        umbral = filters.threshold_otsu(imagen_gris)
        return 2, umbral, "otsu_forzado"

    hist, _ = np.histogram(imagen_gris, bins=256, range=(0, 255), density=True)
    hist_smooth = ndimage.gaussian_filter1d(hist, sigma=SIGMA_HIST)
    peaks, _ = find_peaks(
        hist_smooth, prominence=PROMINENCIA_MODAS, distance=DISTANCIA_MODAS
    )
    num_picos = len(peaks)

    if num_picos >= 3:
        try:
            thresholds = filters.threshold_multiotsu(imagen_gris, classes=3)
            umbral = thresholds[0]  # Clase más oscura
            metodo = "multiotsu_3clases"
        except Exception:
            umbral = filters.threshold_otsu(imagen_gris)
            metodo = "multiotsu_fallback_otsu"
    else:
        umbral = filters.threshold_otsu(imagen_gris)
        metodo = "otsu"

    return num_picos, umbral, metodo

def pipeline_watershed_distancia(imagen_gris):
    # 1. Umbral adaptativo según número de modas
    num_picos, thresh_val, metodo_umbral = detectar_modas_hist(imagen_gris)
    mask = imagen_gris < thresh_val
    
    # 2. Limpieza Morfológica (base V3.0 según README)
    # 2.1 eliminar objetos pequeños
    mask = morphology.remove_small_objects(mask, min_size=AREA_MIN_NUCLEO)

    # 2.2 rellenar huecos pequeños dentro de núcleos (mejora morfología interna)
    mask = morphology.remove_small_holes(mask, area_threshold=50)

    # 2.3 erosión suave para reducir halos (mejora precisión de área)
    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.erode(mask.astype(np.uint8), kernel, iterations=1)
    mask = mask > 0  # volver a booleano

    # 3. Transformada de Distancia y detección de picos (marcadores)
    distance = ndimage.distance_transform_edt(mask)
    # Suavizar el mapa de distancia para obtener marcadores más redondeados (V3.2)
    distance_smooth = ndimage.gaussian_filter(distance, sigma=DIST_SMOOTH_SIGMA)
    coords = feature.peak_local_max(distance_smooth, min_distance=MIN_DISTANCE, labels=mask)

    # 5. Detección de Picos (Markers) -> convertir coords a marcadores etiquetados
    mask_peaks = np.zeros(distance.shape, dtype=bool)
    if hasattr(coords, 'size') and coords.size > 0:
        # coords es array (N,2)
        try:
            mask_peaks[tuple(coords.T)] = True
        except Exception:
            # En casos raros coords puede ser lista de tuplas
            for (r, c) in coords:
                mask_peaks[int(r), int(c)] = True

    markers, _ = ndimage.label(mask_peaks)

    # 6. Watershed (usar la distancia original para el watershed para preservar bordes)
    labels = segmentation.watershed(-distance, markers, mask=mask)

    return labels, mask, distance, {"metodo": metodo_umbral, "umbral": float(thresh_val), "modas": num_picos}


def unir_fragmentos_inteligente(labels):
    """
    V3.1: Une núcleos fragmentados que comparten frontera significativa.
    
    Criterio: Si (píxeles_contacto / perímetro_menor) > THRESHOLD_CONTACTO
             → Son el mismo núcleo fragmentado, fusionar.
    
    Optimización: Solo compara núcleos que realmente se tocan.
    """
    if not USAR_UNION_FRAGMENTOS:
        return labels
    
    labels_copia = labels.copy()
    
    # Encontrar vecinos (núcleos que se tocan) usando dilatación
    kernel = np.ones((3, 3), np.uint8)
    
    # Para cada label, encontrar sus vecinos directos
    unique_labels = np.unique(labels_copia)
    unique_labels = unique_labels[unique_labels != 0]  # Excluir fondo
    
    # Diccionario de vecinos: {label: set(vecinos)}
    vecinos = {label: set() for label in unique_labels}
    
    for label in unique_labels:
        # Máscara del núcleo actual
        mask = (labels_copia == label).astype(np.uint8)
        
        # Dilatar 1 píxel
        mask_dil = cv2.dilate(mask, kernel, iterations=1)
        
        # Encontrar qué otros núcleos toca
        mask_borde = mask_dil - mask  # Solo el borde dilatado
        labels_vecinos = labels_copia[mask_borde > 0]
        
        # Añadir vecinos (excluyendo fondo y sí mismo)
        for vecino in np.unique(labels_vecinos):
            if vecino != 0 and vecino != label:
                vecinos[label].add(vecino)
    
    # Calcular propiedades una sola vez
    props_dict = {prop.label: prop for prop in measure.regionprops(labels_copia)}
    
    # Procesar solo pares de vecinos (permitir fusiones encadenadas)
    pares_procesados = set()
    fusiones_realizadas = True
    
    # Iterar hasta que no haya más fusiones posibles
    while fusiones_realizadas:
        fusiones_realizadas = False
        
        for label_i in unique_labels:
            # Obtener el label actual (puede haber cambiado por fusiones)
            current_label_i = labels_copia[labels_copia == label_i]
            if len(current_label_i) == 0:  # Ya fue fusionado completamente
                continue
            current_label_i = current_label_i[0]
            
            for label_j in vecinos[label_i]:
                # Obtener el label actual de j
                current_label_j = labels_copia[labels_copia == label_j]
                if len(current_label_j) == 0:  # Ya fue fusionado completamente
                    continue
                current_label_j = current_label_j[0]
                
                # Si ya son el mismo, saltar
                if current_label_i == current_label_j:
                    continue
                
                # Evitar procesar el mismo par dos veces en esta iteración
                par = tuple(sorted([current_label_i, current_label_j]))
                if par in pares_procesados:
                    continue
                pares_procesados.add(par)
                
                # Verificar que ambos labels aún existen
                if current_label_i not in props_dict or current_label_j not in props_dict:
                    continue
                
                # Obtener propiedades actualizadas
                prop_i = props_dict[current_label_i]
                prop_j = props_dict[current_label_j]
                
                # Máscaras actuales
                mask_i = (labels_copia == current_label_i)
                mask_j = (labels_copia == current_label_j)
                
                # Dilatar ligeramente para contar contacto
                mask_i_dil = cv2.dilate(mask_i.astype(np.uint8), kernel, iterations=1)
                
                # Contar píxeles de contacto
                pixeles_contacto = np.sum(mask_i_dil & mask_j)
                
                if pixeles_contacto > 0:
                    # Contacto relativo al perímetro más pequeño
                    perimetro_min = min(prop_i.perimeter, prop_j.perimeter)
                    
                    if perimetro_min == 0:
                        continue
                    
                    ratio_contacto = pixeles_contacto / perimetro_min
                    
                    # Si contacto es significativo → FUSIONAR
                    if ratio_contacto > THRESHOLD_CONTACTO:
                        # Fusionar: asignar todos los píxeles de j a i
                        labels_copia[mask_j] = current_label_i
                        fusiones_realizadas = True
                        
                        # Actualizar propiedades (recalcular para el núcleo fusionado)
                        props_fusionado = measure.regionprops((labels_copia == current_label_i).astype(int))
                        if props_fusionado:
                            props_dict[current_label_i] = props_fusionado[0]
                        
                        # Marcar que j ya no existe
                        if current_label_j in props_dict:
                            del props_dict[current_label_j]
        
        # Limpiar pares procesados para la siguiente iteración
        if fusiones_realizadas:
            pares_procesados.clear()
    
    return labels_copia


def rellenar_por_contorno(labels):
    """
    V3.1 Punto 2: Rellena núcleos usando sus contornos.
    
    Para cada núcleo:
    1. Extrae su contorno externo
    2. Rellena todo el interior del contorno
    
    Ventaja sobre remove_small_holes:
    - Más robusto: rellena TODOS los huecos internos sin importar tamaño
    - Núcleos más completos y realistas
    - Área más precisa
    """
    if not USAR_RELLENO_CONTORNO:
        return labels
    
    labels_rellenado = labels.copy()
    
    # Obtener labels únicos (excluyendo fondo)
    unique_labels = np.unique(labels_rellenado)
    unique_labels = unique_labels[unique_labels != 0]
    
    for label in unique_labels:
        # Máscara del núcleo actual
        mask_nucleo = (labels_rellenado == label).astype(np.uint8)
        
        # Encontrar contornos
        contours, _ = cv2.findContours(
            mask_nucleo, 
            cv2.RETR_EXTERNAL,  # Solo contorno externo
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        if contours:
            # Crear máscara vacía
            mask_rellenado = np.zeros_like(mask_nucleo)
            
            # Rellenar el contorno (todos los píxeles dentro)
            cv2.drawContours(
                mask_rellenado, 
                contours, 
                -1,  # Todos los contornos
                1,   # Color (1 para máscara binaria)
                cv2.FILLED  # Rellenar
            )
            
            # Actualizar labels: asignar el label a todos los píxeles rellenados
            labels_rellenado[mask_rellenado > 0] = label
    
    return labels_rellenado


def crear_imagen_coloreada(labels, imagen_original):
    """
    Genera la imagen que 'evaluar_pixel_a_pixel.py' necesita.
    Fondo = Negro (0), Núcleos = Colores aleatorios.
    """
    imagen_coloreada = np.zeros_like(imagen_original)
    unique_labels = np.unique(labels)
    unique_labels = unique_labels[unique_labels != 0]

    np.random.seed(42)
    for label_id in unique_labels:
        color = np.random.randint(
            50, 255, 3
        ).tolist()  # Colores brillantes para evitar negros
        imagen_coloreada[labels == label_id] = color

    return imagen_coloreada


def guardar_resultados_compatible(
    nombre_imagen,
    imagen_original,
    imagen_gris,
    mask_binaria,
    imagen_distancia,
    imagen_coloreada,
    num_nucleos,
):
    base_name = os.path.splitext(nombre_imagen)[0]
    carpeta_imagen = f"{OUTPUT_DIR}/{base_name}"
    Path(carpeta_imagen).mkdir(parents=True, exist_ok=True)

    # Visualización de distancia
    dist_vis = cv2.normalize(imagen_distancia, None, 0, 255, cv2.NORM_MINMAX).astype(
        np.uint8
    )
    dist_vis_color = cv2.applyColorMap(dist_vis, cv2.COLORMAP_JET)
    mask_vis = util.img_as_ubyte(mask_binaria)

    # GUARDAR IMÁGENES
    cv2.imwrite(f"{carpeta_imagen}/1_original_gris.png", imagen_gris)
    cv2.imwrite(f"{carpeta_imagen}/2_mascara_binaria.png", mask_vis)
    cv2.imwrite(f"{carpeta_imagen}/3_mapa_distancia.png", dist_vis_color)

    # ¡IMPORTANTE! Este es el nombre exacto que busca tu script de evaluación:
    cv2.imwrite(f"{carpeta_imagen}/4_coloreada.png", imagen_coloreada)

def guardar_csv(resultados):
    """Guarda el CSV con la columna 'Imagen' que necesita el evaluador"""
    with open(RESULTADOS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Cabeceras compatibles con tu script de evaluación
        writer.writerow(
            ["Imagen", "Num_Nucleos", "Area_Media_px2", "Area_Min_px2", "Area_Max_px2"]
        )

        for res in resultados:
            areas = res["areas_individuales"]
            writer.writerow(
                [
                    res["nombre"],
                    res["num_nucleos"],
                    f"{res['area_media']:.2f}",
                    min(areas) if areas else 0,
                    max(areas) if areas else 0,
                ]
            )


def procesar_todas_imagenes():
    imagenes = sorted(
        list(Path(INPUT_DIR).glob("*.png"))
        + list(Path(INPUT_DIR).glob("*.jpg"))
        + list(Path(INPUT_DIR).glob("*.tif"))
    )

    if not imagenes:
        print(f"ERROR: No se encontraron imágenes en {INPUT_DIR}")
        return

    print(f"Procesando {len(imagenes)} imágenes para evaluación posterior...")
    resultados = []

    for i, ruta in enumerate(imagenes, 1):
        print(f"[{i}/{len(imagenes)}] {ruta.name}...", end=" ", flush=True)
        try:
            nombre_img = ruta.name

            # 1. Cargar imagen
            imagen_original, imagen_gris = cargar_imagen(str(ruta))

            # 2. Algoritmo Watershed + Distancia (V3.2 entregable)
            labels, mask, distance, info_umbral = pipeline_watershed_distancia(imagen_gris)

            # 3. Post-procesado: unir fragmentos significativos y rellenar por contorno
            labels = unir_fragmentos_inteligente(labels)
            labels = rellenar_por_contorno(labels)

            # 5. Colorear
            imagen_coloreada = crear_imagen_coloreada(labels, imagen_original)

            # 6. Estadísticas
            props = measure.regionprops(labels)
            areas = [p.area for p in props]

            # 7. Guardar
            guardar_resultados_compatible(
                nombre_img,
                imagen_original,
                imagen_gris,
                mask,
                distance,
                imagen_coloreada,
                len(areas),
            )

            resultados.append(
                {
                    "nombre": nombre_img,
                    "num_nucleos": len(areas),
                    "area_media": np.mean(areas) if areas else 0,
                    "areas_individuales": areas,
                }
            )
            print(f"OK (umbral={info_umbral['metodo']} modas={info_umbral['modas']} thr={info_umbral['umbral']:.1f})")

        except Exception as e:
            print(f"ERROR: {e}")

    guardar_csv(resultados)
    print(f"\nProceso completado. Ahora puedes ejecutar 'evaluar_pixel_a_pixel.py'.")


if __name__ == "__main__":
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    procesar_todas_imagenes()
