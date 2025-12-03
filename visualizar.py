"""
Visualización de resultados de segmentación.

Flujo por imagen:
1) Carga pasos intermedios generados por segmentar.py (gris, máscara, mapa de distancia, coloreada).
2) Carga GT coloreado y los binariza ambos.
3) Genera: mapa de diferencias FP/FN/TP, contornos GT vs pred, comparativa lado a lado y grid 2×2.
4) Guarda salidas en `visualizaciones/<img>/` y copia del grid en `visualizaciones/RESULTADOS/`.
"""

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np

OUTPUT_DIR = "visualizaciones"
GT_COLORS_DIR = "Material Celulas/gt_colors"
VISUALIZACIONES_DIR = "visualizaciones"
RESULTADOS_DIR = Path(VISUALIZACIONES_DIR) / "RESULTADOS"


def binarizar_imagen(imagen: np.ndarray) -> np.ndarray:
    """Convierte imagen coloreada a binaria (255 núcleos / 0 fondo)."""
    gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen
    _, binaria = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    return binaria


def generar_imagen_diferencias(pred_binaria: np.ndarray, gt_binaria: np.ndarray) -> np.ndarray:
    """Devuelve mapa RGB: FN=rojo, TP=verde, FP=azul."""
    pred = (pred_binaria > 0).astype(bool)
    gt = (gt_binaria > 0).astype(bool)
    h, w = pred.shape
    diff = np.zeros((h, w, 3), dtype=np.uint8)
    diff[(~pred) & gt] = [0, 0, 255]    # FN
    diff[pred & gt] = [0, 255, 0]       # TP
    diff[pred & (~gt)] = [255, 0, 0]    # FP
    return diff


def generar_contornos_superpuestos(imagen_original, pred_color, gt_color) -> np.ndarray:
    """Dibuja contornos GT (rojo) y pred (verde) sobre la imagen original."""
    base = cv2.cvtColor(imagen_original, cv2.COLOR_GRAY2BGR) if imagen_original.ndim == 2 else imagen_original.copy()
    pred_bin = binarizar_imagen(pred_color)
    gt_bin = binarizar_imagen(gt_color)
    contours_pred, _ = cv2.findContours(pred_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours_gt, _ = cv2.findContours(gt_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(base, contours_gt, -1, (0, 0, 255), 2)
    cv2.drawContours(base, contours_pred, -1, (0, 255, 0), 1)
    cv2.putText(base, "GT (rojo) | Pred (verde)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(base, "GT (rojo) | Pred (verde)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
    return base


def generar_comparativa_lado_a_lado(pred_color, gt_color) -> np.ndarray:
    """Concatena predicción y GT, asegurando mismo tamaño."""
    if pred_color.shape != gt_color.shape:
        pred_color = cv2.resize(pred_color, (gt_color.shape[1], gt_color.shape[0]))
    comparativa = np.hstack([pred_color, gt_color])
    h, w = pred_color.shape[:2]
    cv2.putText(comparativa, "PREDICCION", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 3)
    cv2.putText(comparativa, "PREDICCION", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 1)
    cv2.putText(comparativa, "GROUND TRUTH", (w + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 3)
    cv2.putText(comparativa, "GROUND TRUTH", (w + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 1)
    return comparativa


def generar_grid_completo(imagen_gris, mascara_binaria, mapa_distancia, pred_color, gt_color, imagen_diferencias):
    """Grid 2×2: gris | máscara | coloreada | diferencias."""
    h, w = imagen_gris.shape

    def resize_and_convert(img):
        if img.ndim == 2:
            img_c = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        else:
            img_c = img
        if img_c.shape[:2] != (h, w):
            img_c = cv2.resize(img_c, (w, h))
        return img_c

    img1 = resize_and_convert(imagen_gris)
    img2 = resize_and_convert(mascara_binaria)
    img3 = resize_and_convert(pred_color)
    img4 = resize_and_convert(imagen_diferencias)

    titulos = [
        "1. Original (Gris)",
        "2. Mascara Binaria",
        "3. Resultado Coloreado",
        "4. Diferencias (Verde=TP, Azul=FP, Rojo=FN)",
    ]
    for img, titulo in zip([img1, img2, img3, img4], titulos):
        cv2.putText(img, titulo, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv2.putText(img, titulo, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    fila1 = np.hstack([img1, img2])
    fila2 = np.hstack([img3, img4])
    return np.vstack([fila1, fila2])


def procesar_imagen(nombre_imagen: str, verbose: bool = False) -> bool:
    """Genera todas las visualizaciones para una imagen concreta."""
    nombre_base = Path(nombre_imagen).stem
    carpeta_out = Path(OUTPUT_DIR) / nombre_base
    carpeta_vis = Path(VISUALIZACIONES_DIR) / nombre_base
    carpeta_vis.mkdir(parents=True, exist_ok=True)
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    ruta_gris = carpeta_out / "1_original_gris.png"
    ruta_mascara = carpeta_out / "2_mascara_binaria.png"
    ruta_distancia = carpeta_out / "3_mapa_distancia.png"
    ruta_pred = carpeta_out / "4_coloreada.png"
    ruta_gt = Path(GT_COLORS_DIR) / nombre_imagen

    for ruta in [ruta_gris, ruta_mascara, ruta_distancia, ruta_pred, ruta_gt]:
        if not ruta.exists():
            print(f"❌ Falta: {ruta}")
            return False

    imagen_gris = cv2.imread(str(ruta_gris), cv2.IMREAD_GRAYSCALE)
    mascara_binaria = cv2.imread(str(ruta_mascara), cv2.IMREAD_GRAYSCALE)
    mapa_distancia = cv2.imread(str(ruta_distancia))
    pred_color = cv2.imread(str(ruta_pred))
    gt_color = cv2.imread(str(ruta_gt))

    pred_binaria = binarizar_imagen(pred_color)
    gt_binaria = binarizar_imagen(gt_color)
    if pred_binaria.shape != gt_binaria.shape:
        pred_binaria = cv2.resize(pred_binaria, (gt_binaria.shape[1], gt_binaria.shape[0]))
        pred_color = cv2.resize(pred_color, (gt_binaria.shape[1], gt_binaria.shape[0]))

    imagen_diferencias = generar_imagen_diferencias(pred_binaria, gt_binaria)
    contornos_super = generar_contornos_superpuestos(imagen_gris, pred_color, gt_color)
    comparativa = generar_comparativa_lado_a_lado(pred_color, gt_color)
    grid = generar_grid_completo(imagen_gris, mascara_binaria, mapa_distancia, pred_color, gt_color, imagen_diferencias)

    cv2.imwrite(str(carpeta_vis / "diferencias.png"), imagen_diferencias)
    cv2.imwrite(str(carpeta_vis / "contornos_superpuestos.png"), contornos_super)
    cv2.imwrite(str(carpeta_vis / "comparativa_lado_a_lado.png"), comparativa)
    cv2.imwrite(str(carpeta_vis / "grid_completo.png"), grid)
    cv2.imwrite(str(RESULTADOS_DIR / f"{nombre_base}_grid.png"), grid)

    if verbose:
        print(f"  ✓ Diferencias: {carpeta_vis / 'diferencias.png'}")
        print(f"  ✓ Contornos: {carpeta_vis / 'contornos_superpuestos.png'}")
        print(f"  ✓ Comparativa: {carpeta_vis / 'comparativa_lado_a_lado.png'}")
        print(f"  ✓ Grid completo: {carpeta_vis / 'grid_completo.png'}")
    return True


def listar_imagenes_disponibles():
    """Devuelve nombres de imágenes procesadas (carpetas en visualizaciones/)."""
    out_path = Path(OUTPUT_DIR)
    if not out_path.exists():
        return []
    imagenes = []
    for carpeta in out_path.iterdir():
        if carpeta.is_dir() and (carpeta / "4_coloreada.png").exists():
            imagenes.append(carpeta.name + ".png")
    return sorted(imagenes)


def main():
    parser = argparse.ArgumentParser(description="Genera visualizaciones de análisis a partir de resultados de segmentación")
    parser.add_argument("imagen", nargs="?", help="Nombre de imagen específica a procesar")
    parser.add_argument("--listar", "-l", action="store_true", help="Lista imágenes disponibles")
    args = parser.parse_args()

    if args.listar:
        imagenes = listar_imagenes_disponibles()
        if imagenes:
            print(f"\n📁 Imágenes disponibles ({len(imagenes)}):")
            for img in imagenes:
                print(f"  • {img}")
        else:
            print("❌ No hay imágenes procesadas en visualizaciones/")
        return

    if args.imagen:
        print(f"\n🔬 Generando visualizaciones para: {args.imagen}")
        if not procesar_imagen(args.imagen, verbose=True):
            sys.exit(1)
        return

    imagenes = listar_imagenes_disponibles()
    if not imagenes:
        print("❌ No hay imágenes procesadas en visualizaciones/")
        print("   Ejecuta primero: make segmentar")
        sys.exit(1)

    print(f"\n🔬 Generando visualizaciones para {len(imagenes)} imágenes...")
    exitosos = 0
    for i, imagen in enumerate(imagenes, 1):
        print(f"\n[{i}/{len(imagenes)}] {imagen}", end="")
        if procesar_imagen(imagen, verbose=False):
            print(" ✓")
            exitosos += 1
        else:
            print(" ✗")
    print(f"\n✅ Visualizaciones generadas: {exitosos}")
    print(f"📁 Salida: {VISUALIZACIONES_DIR}/ y {RESULTADOS_DIR}/")


if __name__ == "__main__":
    main()
