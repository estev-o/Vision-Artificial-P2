#!/usr/bin/env python3
"""
Generador de Visualizaciones para Segmentación de Núcleos
=========================================================

Script independiente que genera imágenes de análisis a partir de
resultados ya calculados (predicciones y ground truth).

Salidas generadas:
- Imagen de diferencias (FP=azul, FN=rojo, TP=verde)
- Contornos superpuestos
- Comparativa lado a lado
- Grid resumen completo

Uso: python generar_visualizaciones.py [imagen_especifica.png]
     Si no se especifica imagen, procesa todas las del directorio out/
"""

import cv2
import numpy as np
from pathlib import Path
import sys
import argparse

# ==================== CONFIGURACIÓN ====================
OUTPUT_DIR = "visualizaciones"
GT_COLORS_DIR = "Material Celulas/gt_colors"
VISUALIZACIONES_DIR = "visualizaciones"
# =======================================================


def binarizar_imagen(imagen):
    """Convierte imagen coloreada a binaria (blanco=núcleo, negro=fondo)"""
    if len(imagen.shape) == 3:
        gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    else:
        gray = imagen
    
    _, binaria = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    return binaria


def generar_imagen_diferencias(pred_binaria, gt_binaria):
    """
    Genera imagen de diferencias con código de colores:
    - ROJO: False Negatives (núcleos reales no detectados)
    - VERDE: True Positives (píxeles correctamente detectados)
    - AZUL: False Positives (píxeles detectados incorrectamente)
    - NEGRO: True Negatives (fondo correcto)
    """
    # Convertir a booleano
    pred = (pred_binaria > 0).astype(bool)
    gt = (gt_binaria > 0).astype(bool)
    
    # Crear imagen RGB
    h, w = pred.shape
    imagen_diff = np.zeros((h, w, 3), dtype=np.uint8)
    
    # False Negatives (núcleos perdidos) → ROJO
    fn_mask = (~pred) & gt
    imagen_diff[fn_mask] = [0, 0, 255]
    
    # True Positives (correctos) → VERDE
    tp_mask = pred & gt
    imagen_diff[tp_mask] = [0, 255, 0]
    
    # False Positives (detecciones incorrectas) → AZUL
    fp_mask = pred & (~gt)
    imagen_diff[fp_mask] = [255, 0, 0]
    
    return imagen_diff


def generar_contornos_superpuestos(imagen_original, pred_color, gt_color):
    """
    Superpone contornos de predicción (verde) y GT (rojo) sobre imagen original
    """
    # Preparar imagen base (escala de grises a color)
    if len(imagen_original.shape) == 2:
        base = cv2.cvtColor(imagen_original, cv2.COLOR_GRAY2BGR)
    else:
        base = imagen_original.copy()
    
    # Binarizar predicción y GT
    pred_bin = binarizar_imagen(pred_color)
    gt_bin = binarizar_imagen(gt_color)
    
    # Encontrar contornos
    contours_pred, _ = cv2.findContours(pred_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours_gt, _ = cv2.findContours(gt_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Dibujar contornos GT en ROJO (grosor 2)
    cv2.drawContours(base, contours_gt, -1, (0, 0, 255), 2)
    
    # Dibujar contornos PRED en VERDE (grosor 1)
    cv2.drawContours(base, contours_pred, -1, (0, 255, 0), 1)
    
    # Añadir leyenda
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(base, "GT (rojo) | Pred (verde)", (10, 30), font, 0.7, (255, 255, 255), 2)
    cv2.putText(base, "GT (rojo) | Pred (verde)", (10, 30), font, 0.7, (0, 0, 0), 1)
    
    return base


def generar_comparativa_lado_a_lado(pred_color, gt_color):
    """
    Genera imagen con predicción y GT lado a lado
    """
    # Asegurar mismo tamaño
    if pred_color.shape != gt_color.shape:
        pred_color = cv2.resize(pred_color, (gt_color.shape[1], gt_color.shape[0]))
    
    # Concatenar horizontalmente
    comparativa = np.hstack([pred_color, gt_color])
    
    # Añadir etiquetas
    font = cv2.FONT_HERSHEY_SIMPLEX
    h, w = pred_color.shape[:2]
    
    cv2.putText(comparativa, "PREDICCION", (10, 30), font, 1, (255, 255, 255), 3)
    cv2.putText(comparativa, "PREDICCION", (10, 30), font, 1, (0, 0, 0), 1)
    
    cv2.putText(comparativa, "GROUND TRUTH", (w + 10, 30), font, 1, (255, 255, 255), 3)
    cv2.putText(comparativa, "GROUND TRUTH", (w + 10, 30), font, 1, (0, 0, 0), 1)
    
    return comparativa


def generar_grid_completo(imagen_gris, mascara_binaria, mapa_distancia, 
                         pred_color, gt_color, imagen_diferencias):
    """
    Genera grid 2×2 con las visualizaciones principales:
    [1. Original Gris] [2. Máscara Binaria]
    [3. Resultado Coloreado] [4. Diferencias con GT]
    """
    # Asegurar que todas las imágenes sean del mismo tamaño
    h, w = imagen_gris.shape
    
    def resize_and_convert(img, target_shape):
        """Redimensiona y convierte a color si es necesario"""
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.shape[:2] != target_shape:
            img = cv2.resize(img, (target_shape[1], target_shape[0]))
        return img
    
    # Preparar las 4 imágenes del grid
    img1 = resize_and_convert(imagen_gris, (h, w))          # 1. Original gris
    img2 = resize_and_convert(mascara_binaria, (h, w))      # 2. Máscara binaria
    img3 = resize_and_convert(pred_color, (h, w))           # 3. Resultado coloreado
    img4 = resize_and_convert(imagen_diferencias, (h, w))   # 4. Diferencias
    
    # Añadir títulos
    font = cv2.FONT_HERSHEY_SIMPLEX
    titulos = [
        "1. Original (Escala Grises)",
        "2. Mascara Binaria",
        "3. Resultado Coloreado",
        "4. Diferencias (Verde=TP, Azul=FP, Rojo=FN)"
    ]
    
    imagenes = [img1, img2, img3, img4]
    
    for img, titulo in zip(imagenes, titulos):
        cv2.putText(img, titulo, (10, 30), font, 0.5, (255, 255, 255), 2)
        cv2.putText(img, titulo, (10, 30), font, 0.5, (0, 0, 0), 1)
    
    # Crear grid 2×2
    fila1 = np.hstack([img1, img2])
    fila2 = np.hstack([img3, img4])
    
    grid = np.vstack([fila1, fila2])
    
    return grid


def procesar_imagen(nombre_imagen, verbose=False):
    """
    Genera todas las visualizaciones para una imagen específica
    """
    nombre_base = Path(nombre_imagen).stem
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Procesando: {nombre_imagen}")
        print(f"{'='*60}")
    
    # Directorios
    carpeta_out = Path(OUTPUT_DIR) / nombre_base
    carpeta_vis = Path(VISUALIZACIONES_DIR) / nombre_base
    carpeta_vis.mkdir(parents=True, exist_ok=True)
    
    # ========== CARGAR IMÁGENES ==========
    
    # 1. Original en escala de grises
    ruta_gris = carpeta_out / "1_original_gris.png"
    if not ruta_gris.exists():
        print(f"❌ No existe: {ruta_gris}")
        return False
    imagen_gris = cv2.imread(str(ruta_gris), cv2.IMREAD_GRAYSCALE)
    
    # 2. Máscara binaria
    ruta_mascara = carpeta_out / "2_mascara_binaria.png"
    if not ruta_mascara.exists():
        print(f"❌ No existe: {ruta_mascara}")
        return False
    mascara_binaria = cv2.imread(str(ruta_mascara), cv2.IMREAD_GRAYSCALE)
    
    # 3. Mapa de distancia
    ruta_distancia = carpeta_out / "3_mapa_distancia.png"
    if not ruta_distancia.exists():
        print(f"❌ No existe: {ruta_distancia}")
        return False
    mapa_distancia = cv2.imread(str(ruta_distancia))
    
    # 4. Predicción coloreada
    ruta_pred = carpeta_out / "4_coloreada.png"
    if not ruta_pred.exists():
        print(f"❌ No existe: {ruta_pred}")
        return False
    pred_color = cv2.imread(str(ruta_pred))
    
    # 5. Ground Truth
    ruta_gt = Path(GT_COLORS_DIR) / nombre_imagen
    if not ruta_gt.exists():
        print(f"❌ No existe GT: {ruta_gt}")
        return False
    gt_color = cv2.imread(str(ruta_gt))
    
    # Binarizar predicción y GT
    pred_binaria = binarizar_imagen(pred_color)
    gt_binaria = binarizar_imagen(gt_color)
    
    # Asegurar mismo tamaño
    if pred_binaria.shape != gt_binaria.shape:
        pred_binaria = cv2.resize(pred_binaria, (gt_binaria.shape[1], gt_binaria.shape[0]))
        pred_color = cv2.resize(pred_color, (gt_binaria.shape[1], gt_binaria.shape[0]))
    
    # ========== GENERAR VISUALIZACIONES ==========
    
    if verbose:
        print("\n📊 Generando visualizaciones...")
    
    # 1. Imagen de diferencias (FP/FN/TP)
    imagen_diferencias = generar_imagen_diferencias(pred_binaria, gt_binaria)
    ruta_diff = carpeta_vis / "diferencias.png"
    cv2.imwrite(str(ruta_diff), imagen_diferencias)
    if verbose:
        print(f"  ✓ Diferencias: {ruta_diff}")
    
    # 2. Contornos superpuestos
    contornos_super = generar_contornos_superpuestos(imagen_gris, pred_color, gt_color)
    ruta_contornos = carpeta_vis / "contornos_superpuestos.png"
    cv2.imwrite(str(ruta_contornos), contornos_super)
    if verbose:
        print(f"  ✓ Contornos: {ruta_contornos}")
    
    # 3. Comparativa lado a lado
    comparativa = generar_comparativa_lado_a_lado(pred_color, gt_color)
    ruta_comparativa = carpeta_vis / "comparativa_lado_a_lado.png"
    cv2.imwrite(str(ruta_comparativa), comparativa)
    if verbose:
        print(f"  ✓ Comparativa: {ruta_comparativa}")
    
    # 4. Grid completo
    grid = generar_grid_completo(imagen_gris, mascara_binaria, mapa_distancia,
                                pred_color, gt_color, imagen_diferencias)
    ruta_grid = carpeta_vis / "grid_completo.png"
    cv2.imwrite(str(ruta_grid), grid)
    if verbose:
        print(f"  ✓ Grid completo: {ruta_grid}")
    
    if verbose:
        print(f"\n✅ Visualizaciones generadas en: {carpeta_vis}/")
    
    return True


def listar_imagenes_disponibles():
    """Lista todas las imágenes procesadas en el directorio out/"""
    out_path = Path(OUTPUT_DIR)
    if not out_path.exists():
        return []
    
    # Obtener nombres de carpetas en out/ y reconstruir nombre de imagen
    imagenes = []
    for carpeta in out_path.iterdir():
        if carpeta.is_dir():
            # Buscar archivo coloreado para confirmar que está procesada
            if (carpeta / "4_coloreada.png").exists():
                # Reconstruir nombre de imagen (asumimos .png)
                nombre_imagen = carpeta.name + ".png"
                imagenes.append(nombre_imagen)
    
    return sorted(imagenes)


def main():
    parser = argparse.ArgumentParser(
        description='Genera visualizaciones de análisis a partir de resultados de segmentación',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python generar_visualizaciones.py                    # Procesa todas las imágenes
  python generar_visualizaciones.py imagen.png          # Procesa solo imagen.png
  python generar_visualizaciones.py --listar           # Lista imágenes disponibles
        """
    )
    
    parser.add_argument('imagen', nargs='?', help='Nombre de imagen específica a procesar')
    parser.add_argument('--listar', '-l', action='store_true', 
                       help='Lista todas las imágenes disponibles')
    
    args = parser.parse_args()
    
    # Listar imágenes disponibles
    if args.listar:
        imagenes = listar_imagenes_disponibles()
        if imagenes:
            print(f"\n📁 Imágenes disponibles ({len(imagenes)}):")
            for img in imagenes:
                print(f"  • {img}")
        else:
            print("❌ No hay imágenes procesadas en out/")
        return
    
    # Procesar imagen específica
    if args.imagen:
        print(f"\n🔬 Generando visualizaciones para: {args.imagen}")
        exito = procesar_imagen(args.imagen)
        if not exito:
            sys.exit(1)
        return
    
    # Procesar todas las imágenes
    imagenes = listar_imagenes_disponibles()
    
    if not imagenes:
        print("❌ No hay imágenes procesadas en out/")
        print("   Ejecuta primero: make segmentar")
        sys.exit(1)
    
    print(f"\n🔬 Generando visualizaciones para {len(imagenes)} imágenes...")
    
    exitosos = 0
    fallidos = 0
    
    for i, imagen in enumerate(imagenes, 1):
        print(f"\n[{i}/{len(imagenes)}] {imagen}", end="")
        if procesar_imagen(imagen, verbose=False):
            print(" ✓")
            exitosos += 1
        else:
            print(" ✗")
            fallidos += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Visualizaciones generadas: {exitosos}")
    if fallidos > 0:
        print(f"❌ Fallidas: {fallidos}")
    print(f"📁 Salida: {VISUALIZACIONES_DIR}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
