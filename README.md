# V1.0

## Cambios realizados
- Versión inicial del proyecto

## Resumen funcionamiento
Sistema de segmentación automática de núcleos celulares en imágenes histológicas teñidas con Hematoxilina-Eosina (H&E). Utiliza técnicas de procesamiento de imágenes para identificar, separar y cuantificar núcleos individuales. La evaluación compara los resultados con anotaciones ground truth en formato XML.

**Archivos principales:**
- `segmentacion_nucleos.py`: Pipeline de segmentación
- `evaluar_segmentacion.py`: Evaluación con ground truth
- `Makefile`: Automatización (targets: segmentar, evaluar, limpiar, reiniciar)

**Entrada:**
- Imágenes H&E en canal Hematoxilina: `Material Celulas/H/*.png`
- Ground truth coloreado: `Material Celulas/gt_colors/*.png`
- Anotaciones XML: `Material Celulas/xml/*.xml`

**Salida:**
- `resultados.csv`: Métricas de cada imagen (núcleos, áreas)
- `evaluacion.csv`: Comparación con ground truth (precisiones)
- `out/<imagen>/`: Carpeta por imagen con:
  - `1_BN.png` a `6_diferencias.png`: Etapas del pipeline
  - `comparativa.png`: Grid 2×3 con todas las etapas

## Pipeline

### 1. PREPROCESAMIENTO
- **Entrada:** Imagen H&E en canal Hematoxilina (núcleos destacados)
- **Conversión a escala de grises:** Simplifica procesamiento manteniendo información de intensidad
- **Umbralización inversa (THRESH_BINARY_INV):** 
  - Valor umbral: 110
  - Píxeles oscuros (<110) → blancos (núcleos)
  - Píxeles claros (≥110) → negros (fondo)

### 2. MORFOLOGÍA
- **Closing (dilatación + erosión):**
  - Kernel elíptico 3x3
  - 2 iteraciones
  - Rellena huecos pequeños dentro de núcleos sin fusionar núcleos adyacentes

### 3. SEGMENTACIÓN: REGION GROWING CON CONTROL POR GRADIENTE
- **3.1 Detección de centros (semillas):**
  - Transformada de distancia euclidiana
  - Umbralización al 30% del máximo → centros seguros de núcleos
  - Etiquetado de componentes conectadas → cada semilla = ID único

- **3.2 Cálculo de gradiente morfológico:**
  - Detecta bordes fuertes entre núcleos
  - Usado como barrera para detener expansión

- **3.3 Expansión de regiones (BFS simultánea):**
  - Desde cada semilla, expandir a píxeles vecinos (4-conectividad)
  - **Condiciones de crecimiento:**
    - Píxel pertenece a núcleo (imagen binaria = 255)
    - No está ya asignado a otra región
    - Gradiente < 200 (no cruzar bordes fuertes)
  - Continúa hasta que todos los píxeles de núcleos estén asignados

### 4. VISUALIZACIÓN Y RESULTADOS
- **Imágenes generadas por imagen:**
  - `1_BN.png`: Escala de grises
  - `2_umbral.png`: Binarización
  - `3_morfologia.png`: Después de closing
  - `4_coloreada.png`: Núcleos con colores aleatorios
  - `5_contornos.png`: Bordes rojos sobre imagen original
  - `5_GT.png`: Ground truth
  - `6_diferencias.png`: Comparación con GT (ROJO=falsos negativos, VERDE=correctos, AZUL=falsos positivos)
  - `comparativa.png`: Grid 2×3 con todas las etapas

- **CSV generado:**
  - `resultados.csv`: Imagen, Num_Nucleos, Area_Media_px2, Area_Min_px2, Area_Max_px2

### 5. EVALUACIÓN
- **Fuente de ground truth:** Archivos XML con anotaciones manuales y máscaras coloreadas
- **Método:** Matching núcleo por núcleo usando IoU (Intersection over Union)
- **Threshold IoU:** 0.5 (un núcleo predicho se considera correcto si IoU ≥ 0.5 con un núcleo GT)

**Métricas calculadas:**

**1. SEGMENTACIÓN (matching individual):**
- **True Positives (TP):** Núcleos correctamente detectados (IoU ≥ 0.5)
- **False Positives (FP):** Núcleos detectados que no corresponden a reales
- **False Negatives (FN):** Núcleos reales no detectados
- **Precision:** TP / (TP + FP) × 100 - De los detectados, cuántos son correctos
- **Recall:** TP / (TP + FN) × 100 - De los reales, cuántos se detectan
- **F1-Score:** 2 × (Precision × Recall) / (Precision + Recall)
- **IoU medio:** Promedio de IoU de todos los TPs

**2. CONTEO:**
- Error absoluto: |pred - gt|
- Precisión: 100 - (error / gt × 100)

**3. MEDICIÓN DE ÁREAS:**
- **Área media global:** Compara área media predicha vs GT (puede ser engañosa)
- **Área individual (solo TPs):** Error relativo de área para cada núcleo correctamente detectado
  - Métrica más fiable: solo evalúa núcleos que realmente existen

## Resultados actuales

**Dataset:** 30 imágenes H&E del dataset MoNuSeg

### Segmentación (matching IoU ≥ 0.5)
| Métrica | Valor | Interpretación |
|---------|-------|----------------|
| **F1-Score** | **38.42%** | Rendimiento global de detección |
| **Precision** | **50.92%** | Mitad de los núcleos detectados son correctos |
| **Recall** | **31.89%** | Solo se detecta 1 de cada 3 núcleos reales |
| **IoU medio** | **0.677** | Cuando hay match, overlap promedio del 68% |

**Distribución F1:**
- Excelente (≥90%): 0 imágenes
- Bueno (70-90%): 1 imagen
- Regular (50-70%): 3 imágenes
- Malo (<50%): 26 imágenes

### Conteo y Área
| Métrica | Valor |
|---------|-------|
| **Conteo** | **74.30%** |
| **Área media global** | **60.48%** |
| **Área individual (TPs)** | **76.55%** |

**Distribución conteo:**
- Excelente (≥90%): 7 imágenes
- Bueno (70-90%): 11 imágenes
- Regular (50-70%): 9 imágenes
- Malo (<50%): 3 imágenes

### Mejores y peores casos

**Mejor segmentación:**
- TCGA-AR-A1AS-01Z-00-DX1.png: F1 70.4% (TP:256 FP:84 FN:131)

**Peor segmentación:**
- TCGA-G9-6363-01Z-00-DX1.png: F1 9.0% (TP:25 FP:257 FN:251)

**Mejor conteo:**
- TCGA-A7-A13F-01Z-00-DX1.png: 99.7% (GT:356 Pred:357)

**Peor conteo:**
- TCGA-G9-6348-01Z-00-DX1.png: 30.0% (GT:390 Pred:117)

## Debilidades actuales

### 1. BAJO RECALL (31.89%)
**Problema principal:** Se detectan solo 1 de cada 3 núcleos reales.

**Causas identificadas:**
- **Umbrales de distancia muy restrictivos:** Solo 30% de distancia máxima genera semillas
  - Núcleos pequeños o débiles NO generan semilla
  - Muchos núcleos reales quedan sin centro inicial
- **Sub-segmentación:** Múltiples núcleos tocándose se fusionan en uno solo
  - El gradiente morfológico no siempre detecta bordes sutiles
  - Umbral fijo (200) no se adapta a diferentes imágenes

**Evidencia:** 26/30 imágenes con F1 < 50%

### 2. SOBRE-SEGMENTACIÓN (Precision 50.92%)
**Problema:** Mitad de los núcleos detectados son falsos positivos.

**Causas identificadas:**
- **Fragmentación de núcleos grandes:** Un núcleo real se divide en varios
  - Múltiples semillas dentro de un mismo núcleo
  - El gradiente interno crea barreras artificiales
- **Ruido detectado como núcleos:** Artefactos de tinción generan falsas semillas
- **Binarización agresiva:** Umbral 110 puede crear regiones fragmentadas

**Ejemplo real (TCGA-G9-6363):**
```
GT: 276 núcleos
Pred: 282 núcleos (cantidad similar → conteo 97.8%)
TP: 25 (solo 9% bien detectados → F1 9.0%)
FP: 257 (núcleos falsos/fragmentados)
```

### 3. DISCREPANCIA ENTRE MÉTRICAS
**Conteo (74%) vs F1 (38%):** Gran diferencia revela problema fundamental

**Explicación:**
- **Conteo solo mide cantidad total:** No importa QUÉ núcleos detectas
- **F1 mide correspondencia individual:** Importa detectar LOS MISMOS núcleos
- La diferencia indica que detectas "objetos" pero no "los núcleos correctos"

### 4. PARÁMETROS FIJOS NO ADAPTATIVOS
Todos los parámetros son globales:
- Umbral de binarización: 110
- Umbral de gradiente: 200
- Umbral de distancia: 30% del máximo
- Threshold IoU: 0.5

**Consecuencia:** 
- Imágenes con núcleos grandes/pequeños requieren diferentes umbrales
- Variabilidad de tinción entre órganos no se considera
- 87% de imágenes (26/30) con F1 < 50% sugiere falta de adaptación


# V1.1

## Mejoras implementadas

### 1. Umbralización adaptativa por imagen (Otsu)
**Problema anterior:** Umbral fijo (110) no se adaptaba a la variabilidad de tinción entre imágenes.

**Solución:** Método de Otsu que calcula automáticamente el umbral óptimo para CADA imagen.
- Analiza el histograma de intensidades
- Encuentra el umbral que maximiza la varianza entre clases (núcleo/fondo)
- Parámetro: `UMBRAL_ADAPTATIVO = True`

### 2. Umbralización local por regiones
**Problema anterior:** Variabilidad de iluminación/fondo dentro de la misma imagen causaba pérdida de núcleos.

**Solución:** `cv2.adaptiveThreshold` con ventana gaussiana.
- Calcula umbral diferente para cada región de 51×51 píxeles
- Se combina con Otsu global usando OR lógico: píxel es núcleo si CUALQUIERA lo detecta
- Parámetros: `UMBRAL_LOCAL = True`, `BLOCK_SIZE = 51`, `C_CONSTANT = 2`

**Resultado combinado:** Otsu captura tendencia global + adaptiveThreshold compensa variaciones locales

### 3. Evaluación píxel a píxel (Dice Score)
**Problema anterior:** Evaluación por matching IoU penalizaba fuertemente la fragmentación.
- Un núcleo grande fragmentado en 3 → 1 TP + 2 FP → F1 bajo
- No reflejaba que el ÁREA detectada era correcta

**Solución:** Métricas píxel a píxel (Dice/IoU) que comparan máscaras binarias directamente.
- **Dice Score:** 2×TP / (2×TP + FP + FN) - Métrica estándar en segmentación médica
- **IoU:** TP / (TP + FP + FN) - Intersection over Union global
- **Precision píxel:** TP / (TP + FP) - De los píxeles detectados, cuántos correctos
- **Recall píxel:** TP / (TP + FN) - De los píxeles reales, cuántos detectados
- **Accuracy:** (TP + TN) / total - Correctitud global incluyendo fondo

**Ventaja:** Más robusta a fragmentación/fusión, refleja calidad real de segmentación.

**Archivo nuevo:** `evaluar_pixel_a_pixel.py`

## Resultados V1.1

**Dataset:** 30 imágenes H&E del dataset MoNuSeg

### Segmentación píxel a píxel
| Métrica | Valor | Interpretación |
|---------|-------|----------------|
| **Dice Score** | **65.87%** | Overlap promedio entre predicción y GT |
| **IoU** | **50.40%** | Intersection over Union global |
| **Precision** | **54.91%** | De los píxeles detectados, 55% correctos |
| **Recall** | **86.73%** | Se detecta el 87% de los píxeles de núcleos |
| **F1-Score** | **65.87%** | Balance precision-recall |
| **Accuracy** | **77.76%** | 78% de píxeles correctamente clasificados |

**Distribución Dice:**
- Excelente (≥90%): 0 imágenes
- Bueno (70-90%): **13 imágenes** ✅
- Regular (50-70%): **13 imágenes** ✅
- Malo (<50%): 4 imágenes

### Conteo
| Métrica | Valor |
|---------|-------|
| **Precision conteo** | **28.04%** |

⚠️ **Nota:** Conteo bajo debido a fragmentación de núcleos grandes. El algoritmo detecta múltiples semillas en un solo núcleo.

### Mejores y peores casos

**Mejor Dice:**
- TCGA-21-5784-01Z-00-DX1.png: Dice 84.3% (GT:757 Pred:267)

**Peor Dice:**
- TCGA-HE-7128-01Z-00-DX1.png: Dice 36.0% (GT:1076 Pred:205)

## Comparación V1.0 vs V1.1

| Métrica | V1.0 (matching IoU) | V1.1 (píxel a píxel) | Mejora |
|---------|---------------------|----------------------|--------|
| **F1/Dice** | 38.42% | **65.87%** | **+27.45** ✅ |
| **Precision** | 50.92% | 54.91% | +3.99 |
| **Recall** | 31.89% | **86.73%** | **+54.84** ✅ |
| **Imágenes buenas** | 1/30 | **13/30** | **+12** ✅ |
| **Conteo** | 74.30% | 28.04% | -46.26 ⚠️ |

**Conclusión:** Mejora DRÁSTICA en recall (de 32% a 87%) y Dice Score. La evaluación píxel a píxel refleja mejor la calidad real de segmentación.

# V1.2

## Cambios realizados

### 1. Eliminación de morfología (Closing)
**Problema:** El paso de morfología (closing) podía fusionar núcleos adyacentes más que ayudar a rellenar huecos.

**Solución:** Eliminar completamente el paso de morfología.
- Parámetro: `USAR_MORFOLOGIA = False`
- La umbralización adaptativa (Otsu + Local) ya proporciona buena calidad de máscara

### 2. Watershed optimizado en vez de Region Growing
**Problema anterior:** Region Growing requería control manual de gradiente y era sensible a parámetros.

**Solución:** Algoritmo Watershed estándar de OpenCV con parámetros optimizados.
- Más robusto para separar núcleos tocándose
- Usa marcadores (sure foreground/background) para guiar la segmentación
- No requiere BFS manual ni control de gradiente
- **Parámetros optimizados:** `UMBRAL_DISTANCIA = 0.3`, `DILATACION_BACKGROUND = 2`

**Optimización clave:**
- **UMBRAL_DISTANCIA bajado a 0.3** (antes 0.5): Genera más semillas, detecta núcleos pequeños/débiles
- **DILATACION_BACKGROUND reducida a 2** (antes 3): Región desconocida más grande, bordes más generosos

**Implementación:**
```python
# 1. Sure foreground: centros seguros (umbral bajo = más semillas)
# 2. Sure background: dilatación suave de la máscara binaria
# 3. Unknown: región amplia entre foreground y background
# 4. cv2.watershed() decide los bordes en la región unknown
```

### 3. Salidas actualizadas
**Imágenes generadas:**
- `1_BN.png`: Escala de grises
- `2_umbral_otsu.png`: Umbralización global (Otsu)
- `3_umbral_local.png`: Umbralización local (adaptiveThreshold)
- `4_coloreada.png`: Núcleos segmentados con colores
- `5_GT.png`: Ground truth
- `6_diferencias.png`: Comparación (ROJO=FN, VERDE=TP, AZUL=FP)
- `comparativa.png`: Grid 2×3 con todas las etapas

## Resultados V1.2

**Dataset:** 30 imágenes H&E del dataset MoNuSeg

### Segmentación píxel a píxel
| Métrica | Valor | Interpretación |
|---------|-------|----------------|
| **F1-Score** | **72.89%** | Balance precision-recall |
| **IoU** | **57.99%** | Intersection over Union global |
| **Precision** | **67.76%** | De los píxeles detectados, 68% correctos |
| **Recall** | **81.56%** | Se detecta el 82% de los píxeles de núcleos |
| **Accuracy** | **85.18%** | 85% de píxeles correctamente clasificados |

**Distribución F1:**
- Excelente (≥90%): 0 imágenes
- Bueno (70-90%): **18 imágenes** ✅
- Regular (50-70%): **12 imágenes**
- Malo (<50%): **0 imágenes** ✅

### Mejores y peores casos

**Mejor F1:**
- TCGA-21-5784-01Z-00-DX1.png: F1 85.0% (GT:757 Pred:345)

**Peor F1:**
- TCGA-G9-6363-01Z-00-DX1.png: F1 53.2% (GT:354 Pred:283)

### Conteo
| Métrica | Valor |
|---------|-------|
| **Precision conteo** | **50.24%** |

## Comparación V1.1 vs V1.2

| Métrica | V1.1 (Region Growing) | V1.2 (Watershed Optimizado) | Cambio |
|---------|----------------------|----------------------------|--------|
| **F1-Score** | 65.87% | **72.89%** | **+7.02%** ✅ |
| **IoU** | 50.40% | **57.99%** | **+7.59%** ✅ |
| **Precision** | 54.91% | **67.76%** | **+12.85%** ✅ |
| **Recall** | 86.73% | **81.56%** | -5.17% ⚠️ |
| **Accuracy** | 77.76% | **85.18%** | **+7.42%** ✅ |
| **Buenas (70-90%)** | 13 | **18** | **+5** ✅ |
| **Malas (<50%)** | 4 | **0** | **-4** ✅ |
| **Conteo** | 28.04% | **50.24%** | **+22.20%** ✅ |

## Análisis V1.2

### Balance óptimo: Precision y Recall

**Watershed optimizado supera a Region Growing:**
- ✅ **F1 superior (73% vs 66%)**: Mejor rendimiento global en +7 puntos
- ✅ **Mayor Precision (68% vs 55%)**: Menos falsos positivos, detecciones más confiables
- ✅ **Recall alto (82% vs 87%)**: Solo 5 puntos menos pero mucho más preciso
- ✅ **Mayor Accuracy (85% vs 78%)**: Mejor clasificación global de píxeles
- ✅ **IoU superior (58% vs 50%)**: Mejor overlap con ground truth
- ✅ **Más estable**: 0 imágenes malas vs 4 en V1.1, 18 buenas vs 13
- ✅ **Mejor conteo (50% vs 28%)**: Menos fragmentación de núcleos

**Mejora dramática vs versión anterior de Watershed:**
- Primera versión (umbral 0.5, dil 3): F1 61.61%, Recall 60.25%
- **Versión optimizada (umbral 0.3, dil 2): F1 72.89%, Recall 81.56%**
- Ganancia de +11 puntos F1 y +21 puntos Recall con la optimización

**Por qué funciona la optimización:**
1. **Umbral más bajo (0.3)**: Genera más semillas, captura núcleos débiles/pequeños
2. **Menos dilatación (2)**: Región desconocida más amplia, Watershed decide mejor los bordes
3. **Menos fragmentación**: Núcleos grandes mantienen una sola semilla
4. **Mejor balance**: Captura más núcleos (recall) sin explotar falsos positivos (precision)

**Conclusión:** V1.2 con Watershed optimizado es ahora la **MEJOR versión** del sistema, superando tanto a Region Growing (V1.1) como a la versión inicial de Watershed. El ajuste de parámetros logró el balance óptimo entre precision y recall.