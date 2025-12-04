"""
Flujo:
1) Cargar canal H en escala de grises.
2) filtro por imagen: Otsu si el histograma tiene 2 picos; Multi-Otsu (3 clases) si detecta mas de 3 picos (usa la clase más oscura).
3) Limpieza previa: elimina ruido (objetos pequeños), rellena huecos y erosiona ligeramente.
4) EDT + suavizado -> picos locales como marcadores -> watershed sobre -EDT.
5) Postprocesado opcional: fusionar fragmentos que comparten borde y rellenar contorno externo.
6) Guardar pasos intermedios y CSV con conteos/áreas.
"""

import csv
import os
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage
from scipy.signal import find_peaks
from skimage import feature, filters, measure, morphology, segmentation, util

# Parametros globales
MIN_DISTANCE = 5            # Distancia mínima entre picos
AREA_MIN_NUCLEO = 50        # Filtro de ruido (px²)
DIST_SMOOTH_SIGMA = 1.2     # Suavizado del mapa de distancia

# filtroización adaptativa por modas (Otsu/Multi-Otsu)
PROMINENCIA_MODAS = 0.001   # Sensibilidad para hallar picos
DISTANCIA_MODAS = 5         # Separación mínima entre picos
SIGMA_HIST = 1.5            # Suavizado del histograma

# Post-procesado
THRESHOLD_CONTACTO = 0.2    # Fusión si contacto > 20% del perímetro

# Directorios
INPUT_DIR = "Material Celulas/H"
OUTPUT_DIR = "visualizaciones"
RESULTADOS_CSV = "resultados.csv"


def cargar_imagen(ruta_imagen: str):
    #Lee la imagen H, devuelve (RGB y gris).
    imagen_color = cv2.imread(ruta_imagen)
    if imagen_color is None:
        raise FileNotFoundError(f"No se pudo leer la imagen: {ruta_imagen}")
    imagen_gris = cv2.cvtColor(imagen_color, cv2.COLOR_BGR2GRAY)
    return imagen_color, imagen_gris


def detectar_modas_hist(imagen_gris: np.ndarray):
    #Detecta nº de modas del histograma y devuelve (num_picos, filtro, metodo)
    hist, _ = np.histogram(imagen_gris, bins=256, range=(0, 255), density=True)
    # Suavizado del histograma
    hist_smooth = ndimage.gaussian_filter1d(hist, sigma=SIGMA_HIST)
    peaks, _ = find_peaks(hist_smooth, prominence=PROMINENCIA_MODAS, distance=DISTANCIA_MODAS)
    num_picos = len(peaks)

    if num_picos >= 3:
        try:
            thresholds = filters.threshold_multiotsu(imagen_gris, classes=3)
            umbral = thresholds[0]  # clase más oscura (la que nos interesa)
            metodo = "multiotsu_3clases"
        except Exception:
            umbral = filters.threshold_otsu(imagen_gris)
            metodo = "otsu"
    else:
        umbral = filters.threshold_otsu(imagen_gris)
        metodo = "otsu"

    return num_picos, umbral, metodo


def pipeline_watershed(imagen_gris: np.ndarray):
    #Segmenta una imagen gris con watershed 
    # 1) Umbral por modas
    num_picos, umbral, metodo_umbral = detectar_modas_hist(imagen_gris)
    # Máscara binaria de la imagen de gris que pasa el umbral
    mask = imagen_gris < umbral

    # 2) Limpieza previa (ruido y huecos)
    mask = morphology.remove_small_objects(mask, min_size=AREA_MIN_NUCLEO)
    mask = morphology.remove_small_holes(mask, area_threshold=50)

    # 3) Distancia + picos -> marcadores
    distance = ndimage.distance_transform_edt(mask)
    distance_smooth = ndimage.gaussian_filter(distance, sigma=DIST_SMOOTH_SIGMA)
    coords = feature.peak_local_max(distance_smooth, min_distance=MIN_DISTANCE, res_wtrshd=mask)

    # Máscara booleana con 1 píxel True por cada pico detectado (candidatos a semilla)
    mask_peaks = np.zeros(distance.shape, dtype=bool)
    if hasattr(coords, "size") and coords.size > 0:
        for (r, c) in np.atleast_2d(coords):
            mask_peaks[int(r), int(c)] = True
    # Etiquetar cada pico con un ID entero distinto (marcadores para watershed)
    markers, _ = ndimage.label(mask_peaks)

    # 4) Watershed
    res_wtrshd = segmentation.watershed(-distance, markers, mask=mask)

    info = {"metodo": metodo_umbral, "filtro": float(umbral), "modas": num_picos}
    # res_wtrshd: imagen segmentada mask: máscara binaria pre watershed distance: mapa de distancia info: info del filtro
    return res_wtrshd, mask, distance, info


def unir_fragmentos(res_wtrshd: np.ndarray):
    #Fusiona núcleos que comparten borde significativo (contacto relativo > THRESHOLD_CONTACTO)
    res_wtrshd_copia = res_wtrshd.copy()
    kernel = np.ones((3, 3), np.uint8)
    unique_res_wtrshd = np.unique(res_wtrshd_copia)
    unique_res_wtrshd = unique_res_wtrshd[unique_res_wtrshd != 0]

    # Encontrar vecinos de cada núcleo (solo los que se tocan)
    vecinos = {label: set() for label in unique_res_wtrshd}
    for label in unique_res_wtrshd:
        mask = (res_wtrshd_copia == label).astype(np.uint8)
        mask_dil = cv2.dilate(mask, kernel, iterations=1)  # Expandir 1 píxel
        mask_borde = mask_dil - mask  # Solo el borde expandido
        res_wtrshd_vecinos = res_wtrshd_copia[mask_borde > 0]  # Qué res_wtrshd toca
        for vecino in np.unique(res_wtrshd_vecinos):
            if vecino != 0 and vecino != label:
                vecinos[label].add(vecino)

    # Calcular propiedades (área, perímetro) de cada núcleo
    props_dict = {prop.label: prop for prop in measure.regionprops(res_wtrshd_copia)}
    pares_procesados = set()
    fusiones_realizadas = True

    # Repetir mientras se sigan fusionando núcleos
    while fusiones_realizadas:
        fusiones_realizadas = False
        for label_i in list(unique_res_wtrshd):
            current_label_i = res_wtrshd_copia[res_wtrshd_copia == label_i]
            if current_label_i.size == 0:  # Ya fusionado
                continue
            current_label_i = current_label_i[0]

            for label_j in vecinos[label_i]:
                current_label_j = res_wtrshd_copia[res_wtrshd_copia == label_j]
                if current_label_j.size == 0:  # Ya fusionado
                    continue
                current_label_j = current_label_j[0]
                if current_label_i == current_label_j:  # Ya son el mismo
                    continue

                par = tuple(sorted([current_label_i, current_label_j]))
                if par in pares_procesados:  # Ya evaluado en esta ronda
                    continue
                pares_procesados.add(par)

                if current_label_i not in props_dict or current_label_j not in props_dict:
                    continue

                prop_i = props_dict[current_label_i]
                prop_j = props_dict[current_label_j]
                mask_i = res_wtrshd_copia == current_label_i
                mask_j = res_wtrshd_copia == current_label_j
                # Dilatar i y contar cuántos píxeles de j toca
                mask_i_dil = cv2.dilate(mask_i.astype(np.uint8), kernel, iterations=1)
                pixeles_contacto = np.sum(mask_i_dil & mask_j)
                if pixeles_contacto == 0:
                    continue

                # Contacto relativo al perímetro del más pequeño
                perimetro_min = min(prop_i.perimeter, prop_j.perimeter)
                if perimetro_min == 0:
                    continue
                ratio_contacto = pixeles_contacto / perimetro_min

                # Si el contacto es > 20% del perímetro menor -> fusionar
                if ratio_contacto > THRESHOLD_CONTACTO:
                    res_wtrshd_copia[mask_j] = current_label_i  # j pasa a ser i
                    fusiones_realizadas = True
                    # Recalcular propiedades del núcleo fusionado
                    props_fusionado = measure.regionprops((res_wtrshd_copia == current_label_i).astype(int))
                    if props_fusionado:
                        props_dict[current_label_i] = props_fusionado[0]
                    if current_label_j in props_dict:
                        del props_dict[current_label_j]

        if fusiones_realizadas:
            pares_procesados.clear()  # Reiniciar para la siguiente ronda

    return res_wtrshd_copia


def rellenar_por_contorno(res_wtrshd: np.ndarray):
    #Rellena huecos internos usando el contorno externo de cada label
    res_wtrshd_rellenado = res_wtrshd.copy()
    unique_res_wtrshd = np.unique(res_wtrshd_rellenado)
    unique_res_wtrshd = unique_res_wtrshd[unique_res_wtrshd != 0]

    for label in unique_res_wtrshd:
        # Máscara del núcleo actual
        mask_nucleo = (res_wtrshd_rellenado == label).astype(np.uint8)
        # Encontrar solo el contorno externo
        contours, _ = cv2.findContours(mask_nucleo, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        # Rellenar todo el interior del contorno (elimina huecos)
        mask_rellenado = np.zeros_like(mask_nucleo)
        cv2.drawContours(mask_rellenado, contours, -1, 1, cv2.FILLED)
        res_wtrshd_rellenado[mask_rellenado > 0] = label

    return res_wtrshd_rellenado


def crear_imagen_coloreada(res_wtrshd: np.ndarray, imagen_original: np.ndarray) -> np.ndarray:
    #Devuelve imagen coloreada por label (fondo negro)
    imagen_coloreada = np.zeros_like(imagen_original)
    unique_res_wtrshd = np.unique(res_wtrshd)
    unique_res_wtrshd = unique_res_wtrshd[unique_res_wtrshd != 0]

    np.random.seed(42)
    for label_id in unique_res_wtrshd:
        color = np.random.randint(50, 255, 3).tolist()
        imagen_coloreada[res_wtrshd == label_id] = color
    return imagen_coloreada


def guardar_resultados(nombre_imagen: str, imagen_original, imagen_gris, mask_binaria, imagen_distancia, imagen_coloreada, num_nucleos: int):
    """Guarda imágenes intermedias y la coloreada en visualizaciones/<img>/"""
    base_name = os.path.splitext(nombre_imagen)[0]
    carpeta_imagen = Path(OUTPUT_DIR) / base_name
    carpeta_imagen.mkdir(parents=True, exist_ok=True)

    dist_vis = cv2.normalize(imagen_distancia, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    dist_vis_color = cv2.applyColorMap(dist_vis, cv2.COLORMAP_JET)
    mask_vis = util.img_as_ubyte(mask_binaria)

    cv2.imwrite(str(carpeta_imagen / "1_original_gris.png"), imagen_gris)
    cv2.imwrite(str(carpeta_imagen / "2_mascara_binaria.png"), mask_vis)
    cv2.imwrite(str(carpeta_imagen / "3_mapa_distancia.png"), dist_vis_color)
    cv2.imwrite(str(carpeta_imagen / "4_coloreada.png"), imagen_coloreada)


def guardar_csv(resultados):
    """Escribe resultados.csv con conteo y áreas por imagen."""
    with open(RESULTADOS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Imagen", "Num_Nucleos", "Area_Media_px2", "Area_Min_px2", "Area_Max_px2"])
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
    #hace la segmentación de todo el lote H y guarda imágenes/CSV.
    imagenes = sorted(Path(INPUT_DIR).glob("*.png"))
    if not imagenes:
        print(f"ERROR: No se encontraron imágenes en {INPUT_DIR}")
        return

    print(f"Procesando {len(imagenes)} imágenes para evaluación posterior...")
    resultados = []

    for i, ruta in enumerate(imagenes, 1):
        print(f"[{i}/{len(imagenes)}] {ruta.name}...", end=" ", flush=True)
        try:
            #1) Cargar imagen
            imagen_original, imagen_gris = cargar_imagen(str(ruta))
            #2) Pipeline watershed
            res_wtrshd, mask, distance, info_filtro = pipeline_watershed(imagen_gris)
            #3) Post-procesado
            res_wtrshd = unir_fragmentos(res_wtrshd)
            res_wtrshd = rellenar_por_contorno(res_wtrshd)

            #4) Resultados y guardado
            imagen_coloreada = crear_imagen_coloreada(res_wtrshd, imagen_original)
            props = measure.regionprops(res_wtrshd)
            areas = [p.area for p in props]

            guardar_resultados(
                ruta.name, imagen_original, imagen_gris, mask, distance, imagen_coloreada, len(areas)
            )

            resultados.append(
                {
                    "nombre": ruta.name,
                    "num_nucleos": len(areas),
                    "area_media": np.mean(areas) if areas else 0,
                    "areas_individuales": areas,
                }
            )
            print(f"OK (filtro={info_filtro['metodo']} modas={info_filtro['modas']} thr={info_filtro['filtro']:.1f})")

        except Exception as e:
            print(f"ERROR: {e}")

    guardar_csv(resultados)

if __name__ == "__main__":
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    procesar_todas_imagenes()
