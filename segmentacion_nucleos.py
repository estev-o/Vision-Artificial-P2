import cv2
import numpy as np
import os
import csv
from pathlib import Path
from scipy import ndimage
from skimage import filters, morphology, segmentation, feature, util, measure

# ==================== PARÁMETROS (Watershed + Distancia) ====================
# Configuración óptima basada en experimentos exhaustivos:
# - MIN_DISTANCE=5: Balance óptimo entre sobre/sub-segmentación (F1: 73.85%)
# - remove_small_holes: Mejora morfología interna sin fusionar núcleos cercanos
# - Basado en análisis GT: 16,819 núcleos, área media 432 px², diámetro ~23.5 px
MIN_DISTANCE = 5  # Distancia mínima entre picos (evita sobre-segmentación)
AREA_MIN_NUCLEO = 50  # Filtro de ruido (P5 del GT = 80 px², usamos 50 para recall)

# Directorios
INPUT_DIR = "Material Celulas/H"
OUTPUT_DIR = "visualizaciones"
GT_DIR = "Material Celulas/gt_colors"
RESULTADOS_CSV = "resultados.csv"
# ============================================================================


def cargar_imagen(ruta_imagen):
    imagen_color = cv2.imread(ruta_imagen)
    if imagen_color is None:
        raise FileNotFoundError(f"No se pudo leer la imagen: {ruta_imagen}")
    imagen_gris = cv2.cvtColor(imagen_color, cv2.COLOR_BGR2GRAY)
    return imagen_color, imagen_gris


def pipeline_watershed_distancia(imagen_gris):
    """
    Pipeline de segmentación basado en Watershed + Distance Transform.
    
    Configuración óptima (F1: 73.85%, Recall: 88.35%, IoU: 59.19%):
    - Otsu global para umbralización robusta en H&E
    - remove_small_holes: Rellena huecos internos mejorando morfología
    - Distance Transform + peak_local_max: Genera markers adaptativos
    - MIN_DISTANCE=5: Evita sobre-segmentación manteniendo alto recall
    - Watershed: Separación final basada en gradiente de distancia
    
    Trade-off conocido: Área ~2x mayor que GT (fusiona núcleos muy cercanos)
    pero excelente F1 y recall por detección robusta.
    """
    # 1. Otsu Global (Estándar robusto para Hematoxilina)
    thresh_val = filters.threshold_otsu(imagen_gris)
    mask = imagen_gris < thresh_val

    # 2. Limpieza Morfológica
    mask = morphology.remove_small_objects(mask, min_size=AREA_MIN_NUCLEO)
    mask = morphology.remove_small_holes(mask, area_threshold=AREA_MIN_NUCLEO)

    # 3. Transformada de Distancia
    distance = ndimage.distance_transform_edt(mask)

    # 4. Detección de Picos (Markers)
    coords = feature.peak_local_max(distance, min_distance=MIN_DISTANCE, labels=mask)
    mask_peaks = np.zeros(distance.shape, dtype=bool)
    mask_peaks[tuple(coords.T)] = True
    markers, _ = ndimage.label(mask_peaks)

    # 5. Watershed
    labels = segmentation.watershed(-distance, markers, mask=mask)

    return labels, mask, distance


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

            # 1. Cargar
            imagen_original, imagen_gris = cargar_imagen(str(ruta))

            # 2. Algoritmo Watershed + Distancia
            labels, mask, distance = pipeline_watershed_distancia(imagen_gris)

            # 3. Colorear
            imagen_coloreada = crear_imagen_coloreada(labels, imagen_original)

            # 4. Estadísticas
            props = measure.regionprops(labels)
            areas = [p.area for p in props]

            # 5. Guardar
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
            print("OK")

        except Exception as e:
            print(f"ERROR: {e}")

    guardar_csv(resultados)
    print(f"\nProceso completado. Ahora puedes ejecutar 'evaluar_pixel_a_pixel.py'.")


if __name__ == "__main__":
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    procesar_todas_imagenes()
