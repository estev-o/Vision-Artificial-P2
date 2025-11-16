import cv2
import numpy as np
import os
import csv
from pathlib import Path

# ==================== PARÁMETROS ====================
UMBRAL_VALOR = 110  # Valor de corte para la umbralización
KERNEL_SIZE = 3
CLOSING_ITERATIONS = 2
UMBRAL_GRADIENTE = 150
UMBRAL_DISTANCIA = 0.3  # Bajado de 0.2 → más semillas, más núcleos pequeños detectados

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
    _, imagen_umbralizada = cv2.threshold(
        imagen_gris, UMBRAL_VALOR, 255, cv2.THRESH_BINARY_INV
    )
    return imagen_umbralizada


def aplicar_closing(imagen_binaria):
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (KERNEL_SIZE, KERNEL_SIZE))
    imagen_closing = cv2.morphologyEx(
        imagen_binaria, cv2.MORPH_CLOSE, kernel, iterations=CLOSING_ITERATIONS
    )
    return imagen_closing


def aplicar_region_growing(imagen_binaria):
    from collections import deque

    # 1. DISTANCIA: Encontrar centros de núcleos
    dist_transform = cv2.distanceTransform(imagen_binaria, cv2.DIST_L2, 5)

    # 2. SEMILLAS: Centros seguros
    _, sure_fg = cv2.threshold(
        dist_transform, UMBRAL_DISTANCIA * dist_transform.max(), 255, cv2.THRESH_BINARY
    )
    sure_fg = sure_fg.astype(np.uint8)

    # 3. ETIQUETAR semillas
    _, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1  # Fondo=1, semillas=2,3,4...

    # 4. GRADIENTE: Detectar bordes fuertes
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    gradiente = cv2.morphologyEx(imagen_binaria, cv2.MORPH_GRADIENT, kernel)

    # 5. REGION GROWING: Expansión simultánea desde semillas
    h, w = imagen_binaria.shape
    cola = deque()

    # Inicializar cola con todos los píxeles de las semillas
    for y in range(h):
        for x in range(w):
            if markers[y, x] > 1:  # Es semilla (no fondo)
                cola.append((y, x, markers[y, x]))

    # Expansión BFS simultánea
    vecinos = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 4-conectividad

    while cola:
        y, x, region_id = cola.popleft()

        for dy, dx in vecinos:
            ny, nx = y + dy, x + dx

            # Verificar límites
            if 0 <= ny < h and 0 <= nx < w:
                # Solo expandir a píxeles de núcleo no asignados
                if imagen_binaria[ny, nx] == 255 and markers[ny, nx] == 1:
                    # Control por gradiente: no cruzar bordes fuertes
                    if gradiente[ny, nx] < UMBRAL_GRADIENTE:
                        markers[ny, nx] = region_id
                        cola.append((ny, nx, region_id))

    # Convertir fondo de 1 a 0
    markers[markers == 1] = 0

    return markers


def crear_imagen_segmentada(markers, imagen_original):
    # COLOREADA: Asignar color aleatorio a cada núcleo
    imagen_coloreada = np.zeros_like(imagen_original)
    ids_nucleos = np.unique(markers)
    ids_nucleos = ids_nucleos[ids_nucleos > 1]

    np.random.seed(42)
    for nucleo_id in ids_nucleos:
        color = np.random.randint(0, 255, 3).tolist()
        imagen_coloreada[markers == nucleo_id] = color

    # CONTORNOS: Dibujar bordes en rojo
    imagen_contornos = (
        cv2.cvtColor(imagen_original, cv2.COLOR_GRAY2BGR)
        if len(imagen_original.shape) == 2
        else imagen_original.copy()
    )
    contornos_mask = (markers == 0) | (markers == -1)
    imagen_contornos[contornos_mask] = [0, 0, 255]

    return imagen_coloreada, imagen_contornos


def guardar_resultados(
    nombre_imagen,
    imagen_original,
    imagen_gris,
    imagen_umbralizada,
    imagen_morfologia,
    imagen_coloreada,
    imagen_contornos,
    num_nucleos,
):
    base_name = os.path.splitext(nombre_imagen)[0]
    carpeta_imagen = f"{OUTPUT_DIR}/{base_name}"
    Path(carpeta_imagen).mkdir(parents=True, exist_ok=True)

    # GUARDAR: Imágenes individuales del pipeline
    cv2.imwrite(f"{carpeta_imagen}/1_BN.png", imagen_gris)
    cv2.imwrite(f"{carpeta_imagen}/2_umbral.png", imagen_umbralizada)
    cv2.imwrite(f"{carpeta_imagen}/3_morfologia.png", imagen_morfologia)
    cv2.imwrite(f"{carpeta_imagen}/4_coloreada.png", imagen_coloreada)
    cv2.imwrite(f"{carpeta_imagen}/5_contornos.png", imagen_contornos)

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
    img_umbral_bgr = cv2.cvtColor(imagen_umbralizada, cv2.COLOR_GRAY2BGR)
    img_morfologia_bgr = cv2.cvtColor(imagen_morfologia, cv2.COLOR_GRAY2BGR)

    h, w = imagen_original.shape[:2]
    scale = 0.4
    new_size = (int(w * scale), int(h * scale))

    img_gris_small = cv2.resize(img_gris_bgr, new_size)
    img_umbral_small = cv2.resize(img_umbral_bgr, new_size)
    img_morfologia_small = cv2.resize(img_morfologia_bgr, new_size)
    img_coloreada_small = cv2.resize(imagen_coloreada, new_size)

    if img_gt is not None:
        img_gt_small = cv2.resize(img_gt, new_size)
    else:
        img_gt_small = np.zeros_like(img_coloreada_small)

    if img_diff is not None:
        img_diff_small = cv2.resize(img_diff, new_size)
    else:
        img_diff_small = np.zeros_like(img_coloreada_small)

    fila1 = np.hstack([img_gris_small, img_umbral_small, img_morfologia_small])
    fila2 = np.hstack([img_coloreada_small, img_gt_small, img_diff_small])
    comparativa = np.vstack([fila1, fila2])

    cv2.imwrite(f"{carpeta_imagen}/comparativa.png", comparativa)


def procesar_imagen(ruta_imagen):
    nombre_imagen = os.path.basename(ruta_imagen)

    # PIPELINE
    imagen_original, imagen_gris = cargar_imagen(ruta_imagen)
    imagen_umbralizada = aplicar_umbralizacion(imagen_gris)
    imagen_morfologia = aplicar_closing(imagen_umbralizada)
    markers = aplicar_region_growing(imagen_morfologia)

    # Calcular núcleos
    ids_nucleos = np.unique(markers)
    ids_nucleos = ids_nucleos[ids_nucleos > 0]  # Excluir fondo
    num_nucleos = len(ids_nucleos)

    areas = []
    for nucleo_id in ids_nucleos:
        area = np.sum(markers == nucleo_id)
        areas.append(area)

    area_media = np.mean(areas) if areas else 0
    imagen_coloreada, imagen_contornos = crear_imagen_segmentada(
        markers, imagen_original
    )

    guardar_resultados(
        nombre_imagen,
        imagen_original,
        imagen_gris,
        imagen_umbralizada,
        imagen_morfologia,
        imagen_coloreada,
        imagen_contornos,
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
