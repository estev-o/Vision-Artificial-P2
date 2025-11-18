#!/usr/bin/env python3
"""
Análisis exhaustivo del Ground Truth (GT) para extraer conocimiento morfométrico.
Estudia formas, tamaños, distribuciones y características de los núcleos reales.
"""

import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict

# Matplotlib opcional
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_DISPONIBLE = True
except ImportError:
    MATPLOTLIB_DISPONIBLE = False
    print("⚠️  Matplotlib no disponible - gráficos desactivados")

# Rutas
GT_DIR = "Material Celulas/gt_colors"
XML_DIR = "Material Celulas/xml"

def analizar_nucleos_gt():
    """
    Analiza todos los núcleos del GT y extrae estadísticas morfométricas.
    """
    # Almacenar todas las métricas
    areas = []
    perimetros = []
    circularidades = []
    solideces = []
    aspect_ratios = []
    anchos = []
    altos = []
    excentricidades = []
    
    # Contadores
    total_nucleos = 0
    total_imagenes = 0
    
    print("="*70)
    print("  ANÁLISIS MORFOMÉTRICO DEL GROUND TRUTH")
    print("="*70)
    
    # Procesar cada imagen GT
    ruta_gt = Path(GT_DIR)
    imagenes_gt = sorted(ruta_gt.glob("*.png"))
    
    for ruta_imagen in imagenes_gt:
        # Cargar GT en color
        img_gt = cv2.imread(str(ruta_imagen))
        if img_gt is None:
            continue
        
        # Convertir a escala de grises
        img_gray = cv2.cvtColor(img_gt, cv2.COLOR_BGR2GRAY)
        
        # Binarizar (GT tiene núcleos en blanco/colores, fondo negro)
        _, img_bin = cv2.threshold(img_gray, 10, 255, cv2.THRESH_BINARY)
        
        # Encontrar componentes conectadas (cada núcleo)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            img_bin, connectivity=8
        )
        
        nucleos_imagen = 0
        
        # Analizar cada núcleo (ignorar fondo = label 0)
        for label_id in range(1, num_labels):
            # Crear máscara del núcleo individual
            mascara = (labels == label_id).astype(np.uint8) * 255
            
            # Encontrar contorno
            contornos, _ = cv2.findContours(
                mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            if len(contornos) == 0 or len(contornos[0]) < 5:
                continue
            
            contorno = contornos[0]
            area = cv2.contourArea(contorno)
            
            # Filtrar ruido (núcleos muy pequeños)
            if area < 50:
                continue
            
            # MÉTRICAS GEOMÉTRICAS
            perimetro = cv2.arcLength(contorno, True)
            x, y, w, h = cv2.boundingRect(contorno)
            hull = cv2.convexHull(contorno)
            area_convexa = cv2.contourArea(hull)
            
            # Ajustar elipse (requiere al menos 5 puntos)
            if len(contorno) >= 5:
                try:
                    elipse = cv2.fitEllipse(contorno)
                    (cx, cy), (MA, ma), angle = elipse
                    # Excentricidad: 0 = círculo, ~1 = muy elongado
                    if MA > 0:
                        excentricidad = np.sqrt(1 - (ma**2 / MA**2)) if MA > ma else 0
                        excentricidades.append(excentricidad)
                except:
                    pass
            
            # CALCULAR MÉTRICAS
            # Circularidad: 4π*A/P² (1.0 = círculo perfecto)
            circularidad = 4 * np.pi * area / (perimetro ** 2) if perimetro > 0 else 0
            
            # Solidez: A/A_convexa (1.0 = sin concavidades)
            solidez = area / area_convexa if area_convexa > 0 else 0
            
            # Aspect Ratio: max(w,h)/min(w,h) (1.0 = cuadrado)
            aspect_ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 0
            
            # Almacenar
            areas.append(area)
            perimetros.append(perimetro)
            circularidades.append(circularidad)
            solideces.append(solidez)
            aspect_ratios.append(aspect_ratio)
            anchos.append(w)
            altos.append(h)
            
            nucleos_imagen += 1
        
        total_nucleos += nucleos_imagen
        total_imagenes += 1
    
    # Convertir a numpy arrays
    areas = np.array(areas)
    perimetros = np.array(perimetros)
    circularidades = np.array(circularidades)
    solideces = np.array(solideces)
    aspect_ratios = np.array(aspect_ratios)
    anchos = np.array(anchos)
    altos = np.array(altos)
    excentricidades = np.array(excentricidades)
    
    # IMPRIMIR ESTADÍSTICAS
    print(f"\n📊 DATASET:")
    print(f"   Total imágenes: {total_imagenes}")
    print(f"   Total núcleos:  {total_nucleos}")
    print(f"   Media por img:  {total_nucleos/total_imagenes:.1f} núcleos")
    
    print(f"\n📏 ÁREA (px²):")
    print(f"   Media:    {np.mean(areas):.2f} px²")
    print(f"   Mediana:  {np.median(areas):.2f} px²")
    print(f"   Std Dev:  {np.std(areas):.2f} px²")
    print(f"   Min:      {np.min(areas):.2f} px²")
    print(f"   Max:      {np.max(areas):.2f} px²")
    print(f"   P25:      {np.percentile(areas, 25):.2f} px²")
    print(f"   P75:      {np.percentile(areas, 75):.2f} px²")
    
    print(f"\n📐 DIMENSIONES (px):")
    print(f"   Ancho medio:  {np.mean(anchos):.2f} px")
    print(f"   Alto medio:   {np.mean(altos):.2f} px")
    print(f"   Diámetro equiv: {np.sqrt(4*np.mean(areas)/np.pi):.2f} px")
    
    print(f"\n⭕ CIRCULARIDAD (1.0 = círculo perfecto):")
    print(f"   Media:    {np.mean(circularidades):.3f}")
    print(f"   Mediana:  {np.median(circularidades):.3f}")
    print(f"   Std Dev:  {np.std(circularidades):.3f}")
    print(f"   P5:       {np.percentile(circularidades, 5):.3f}")
    print(f"   P95:      {np.percentile(circularidades, 95):.3f}")
    
    print(f"\n🔷 SOLIDEZ (1.0 = sin concavidades):")
    print(f"   Media:    {np.mean(solideces):.3f}")
    print(f"   Mediana:  {np.median(solideces):.3f}")
    print(f"   Std Dev:  {np.std(solideces):.3f}")
    print(f"   P5:       {np.percentile(solideces, 5):.3f}")
    print(f"   P95:      {np.percentile(solideces, 95):.3f}")
    
    print(f"\n📊 ASPECT RATIO (1.0 = cuadrado):")
    print(f"   Media:    {np.mean(aspect_ratios):.3f}")
    print(f"   Mediana:  {np.median(aspect_ratios):.3f}")
    print(f"   Std Dev:  {np.std(aspect_ratios):.3f}")
    print(f"   P95:      {np.percentile(aspect_ratios, 95):.3f}")
    print(f"   P99:      {np.percentile(aspect_ratios, 99):.3f}")
    
    if len(excentricidades) > 0:
        print(f"\n🎯 EXCENTRICIDAD (0 = círculo, 1 = línea):")
        print(f"   Media:    {np.mean(excentricidades):.3f}")
        print(f"   Mediana:  {np.median(excentricidades):.3f}")
        print(f"   P95:      {np.percentile(excentricidades, 95):.3f}")
    
    # ANÁLISIS DE DISTRIBUCIONES
    print(f"\n" + "="*70)
    print("  DISTRIBUCIONES POR RANGOS")
    print("="*70)
    
    # Distribución de área
    print(f"\n📏 DISTRIBUCIÓN DE ÁREA:")
    bins_area = [0, 200, 400, 600, 800, 1000, 99999]
    labels_area = ["<200", "200-400", "400-600", "600-800", "800-1000", ">1000"]
    for i, (low, high, label) in enumerate(zip(bins_area[:-1], bins_area[1:], labels_area)):
        count = np.sum((areas >= low) & (areas < high))
        pct = 100 * count / len(areas)
        print(f"   {label:>10} px²: {count:5d} núcleos ({pct:5.1f}%)")
    
    # Distribución de circularidad
    print(f"\n⭕ DISTRIBUCIÓN DE CIRCULARIDAD:")
    bins_circ = [0, 0.3, 0.5, 0.7, 0.85, 1.0]
    labels_circ = ["<0.3 (muy irregular)", "0.3-0.5 (irregular)", "0.5-0.7 (moderado)", 
                   "0.7-0.85 (bueno)", "0.85-1.0 (excelente)"]
    for low, high, label in zip(bins_circ[:-1], bins_circ[1:], labels_circ):
        count = np.sum((circularidades >= low) & (circularidades < high))
        pct = 100 * count / len(circularidades)
        print(f"   {label:25s}: {count:5d} núcleos ({pct:5.1f}%)")
    
    # Distribución de solidez
    print(f"\n🔷 DISTRIBUCIÓN DE SOLIDEZ:")
    bins_sol = [0, 0.7, 0.8, 0.9, 0.95, 1.0]
    labels_sol = ["<0.7 (muchas concavidades)", "0.7-0.8 (concavidades)", 
                  "0.8-0.9 (pocas concavidades)", "0.9-0.95 (muy sólido)", "0.95-1.0 (perfecto)"]
    for low, high, label in zip(bins_sol[:-1], bins_sol[1:], labels_sol):
        count = np.sum((solideces >= low) & (solideces < high))
        pct = 100 * count / len(solideces)
        print(f"   {label:30s}: {count:5d} núcleos ({pct:5.1f}%)")
    
    # Distribución de aspect ratio
    print(f"\n📊 DISTRIBUCIÓN DE ASPECT RATIO:")
    bins_ar = [1.0, 1.5, 2.0, 2.5, 3.0, 99]
    labels_ar = ["1.0-1.5 (circular)", "1.5-2.0 (ligeramente elongado)", 
                 "2.0-2.5 (elongado)", "2.5-3.0 (muy elongado)", ">3.0 (extremo)"]
    for low, high, label in zip(bins_ar[:-1], bins_ar[1:], labels_ar):
        count = np.sum((aspect_ratios >= low) & (aspect_ratios < high))
        pct = 100 * count / len(aspect_ratios)
        print(f"   {label:30s}: {count:5d} núcleos ({pct:5.1f}%)")
    
    # RECOMENDACIONES
    print(f"\n" + "="*70)
    print("  💡 RECOMENDACIONES PARA PARÁMETROS")
    print("="*70)
    
    # Umbral de área mínima
    area_min_recomendada = np.percentile(areas, 5)  # P5
    print(f"\n1️⃣  ÁREA MÍNIMA:")
    print(f"   Actual: 50 px²")
    print(f"   Recomendado: {area_min_recomendada:.0f} px² (P5 del GT)")
    print(f"   Razón: Filtrar ruido sin perder núcleos pequeños reales")
    
    # Umbral de circularidad
    circ_p5 = np.percentile(circularidades, 5)
    print(f"\n2️⃣  CIRCULARIDAD_MIN:")
    print(f"   Actual: 0.3")
    print(f"   P5 del GT: {circ_p5:.3f}")
    print(f"   Recomendado: {circ_p5:.2f}")
    print(f"   Razón: 95% de núcleos GT están por encima de este valor")
    
    # Umbral de solidez
    sol_p5 = np.percentile(solideces, 5)
    print(f"\n3️⃣  SOLIDEZ_MIN:")
    print(f"   Actual: 0.7")
    print(f"   P5 del GT: {sol_p5:.3f}")
    print(f"   Recomendado: {max(0.75, sol_p5):.2f}")
    print(f"   Razón: Detectar concavidades anormales sin ser muy estricto")
    
    # Umbral de aspect ratio
    ar_p95 = np.percentile(aspect_ratios, 95)
    ar_p99 = np.percentile(aspect_ratios, 99)
    print(f"\n4️⃣  ASPECT_RATIO_MAX:")
    print(f"   Actual: 2.5")
    print(f"   P95 del GT: {ar_p95:.2f}")
    print(f"   P99 del GT: {ar_p99:.2f}")
    print(f"   Recomendado: {ar_p95:.1f}")
    print(f"   Razón: 95% de núcleos GT están por debajo (detectar fusiones)")
    
    # Rango de área esperado
    area_p5 = np.percentile(areas, 5)
    area_p95 = np.percentile(areas, 95)
    print(f"\n5️⃣  RANGO DE ÁREA ESPERADO:")
    print(f"   P5-P95: {area_p5:.0f} - {area_p95:.0f} px²")
    print(f"   Uso: Detectar núcleos anómalos (muy grandes/pequeños)")
    
    # Watershed: distancia esperada
    diametro_medio = np.sqrt(4 * np.mean(areas) / np.pi)
    distancia_sugerida = diametro_medio * 0.15  # 15% del diámetro
    print(f"\n6️⃣  WATERSHED - UMBRAL_DISTANCIA:")
    print(f"   Diámetro medio: {diametro_medio:.1f} px")
    print(f"   Distancia mínima entre centros: {distancia_sugerida:.1f} px")
    print(f"   Umbral_distancia actual: 0.25 (relativo)")
    print(f"   Recomendación: Mantener 0.25-0.30 (funciona bien)")
    
    print(f"\n" + "="*70)
    
    # Crear gráficos (si matplotlib está disponible)
    if MATPLOTLIB_DISPONIBLE:
        crear_graficos(areas, circularidades, solideces, aspect_ratios, 
                       anchos, altos, excentricidades)
    else:
        print("\n⚠️  Instala matplotlib para generar gráficos: pip install matplotlib")
    
    return {
        'area_min': area_min_recomendada,
        'circularidad_min': circ_p5,
        'solidez_min': max(0.75, sol_p5),
        'aspect_ratio_max': ar_p95,
        'area_p5': area_p5,
        'area_p95': area_p95,
        'diametro_medio': diametro_medio
    }


def crear_graficos(areas, circularidades, solideces, aspect_ratios, 
                   anchos, altos, excentricidades):
    """
    Crea visualizaciones de las distribuciones.
    """
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle('Análisis Morfométrico del Ground Truth', fontsize=16, fontweight='bold')
    
    # 1. Histograma de áreas
    ax = axes[0, 0]
    ax.hist(areas, bins=50, color='steelblue', edgecolor='black', alpha=0.7)
    ax.axvline(np.mean(areas), color='red', linestyle='--', linewidth=2, label=f'Media: {np.mean(areas):.0f}')
    ax.axvline(np.median(areas), color='green', linestyle='--', linewidth=2, label=f'Mediana: {np.median(areas):.0f}')
    ax.set_xlabel('Área (px²)', fontsize=10)
    ax.set_ylabel('Frecuencia', fontsize=10)
    ax.set_title('Distribución de Área', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 2. Histograma de circularidad
    ax = axes[0, 1]
    ax.hist(circularidades, bins=50, color='coral', edgecolor='black', alpha=0.7)
    ax.axvline(np.mean(circularidades), color='red', linestyle='--', linewidth=2, label=f'Media: {np.mean(circularidades):.3f}')
    ax.axvline(0.7, color='orange', linestyle=':', linewidth=2, label='Umbral: 0.7')
    ax.set_xlabel('Circularidad', fontsize=10)
    ax.set_ylabel('Frecuencia', fontsize=10)
    ax.set_title('Distribución de Circularidad', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 3. Histograma de solidez
    ax = axes[0, 2]
    ax.hist(solideces, bins=50, color='lightgreen', edgecolor='black', alpha=0.7)
    ax.axvline(np.mean(solideces), color='red', linestyle='--', linewidth=2, label=f'Media: {np.mean(solideces):.3f}')
    ax.axvline(0.7, color='orange', linestyle=':', linewidth=2, label='Umbral: 0.7')
    ax.set_xlabel('Solidez', fontsize=10)
    ax.set_ylabel('Frecuencia', fontsize=10)
    ax.set_title('Distribución de Solidez', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 4. Histograma de aspect ratio
    ax = axes[1, 0]
    ax.hist(aspect_ratios, bins=50, color='plum', edgecolor='black', alpha=0.7)
    ax.axvline(np.mean(aspect_ratios), color='red', linestyle='--', linewidth=2, label=f'Media: {np.mean(aspect_ratios):.2f}')
    ax.axvline(2.5, color='orange', linestyle=':', linewidth=2, label='Umbral: 2.5')
    ax.set_xlabel('Aspect Ratio', fontsize=10)
    ax.set_ylabel('Frecuencia', fontsize=10)
    ax.set_title('Distribución de Aspect Ratio', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 5. Scatter: ancho vs alto
    ax = axes[1, 1]
    ax.scatter(anchos, altos, alpha=0.3, s=10, color='dodgerblue')
    ax.plot([0, max(anchos)], [0, max(anchos)], 'r--', linewidth=1, label='1:1 (cuadrado)')
    ax.set_xlabel('Ancho (px)', fontsize=10)
    ax.set_ylabel('Alto (px)', fontsize=10)
    ax.set_title('Ancho vs Alto', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')
    
    # 6. Scatter: área vs circularidad
    ax = axes[1, 2]
    scatter = ax.scatter(areas, circularidades, c=solideces, cmap='viridis', 
                        alpha=0.5, s=10, edgecolors='none')
    ax.set_xlabel('Área (px²)', fontsize=10)
    ax.set_ylabel('Circularidad', fontsize=10)
    ax.set_title('Área vs Circularidad (color=solidez)', fontweight='bold')
    ax.axhline(0.7, color='red', linestyle=':', linewidth=1, alpha=0.5)
    ax.grid(True, alpha=0.3)
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Solidez', fontsize=9)
    
    plt.tight_layout()
    plt.savefig('analisis_gt.png', dpi=150, bbox_inches='tight')
    print(f"\n💾 Gráficos guardados en: analisis_gt.png")
    print(f"   Abre el archivo para visualización detallada")


if __name__ == "__main__":
    parametros = analizar_nucleos_gt()
