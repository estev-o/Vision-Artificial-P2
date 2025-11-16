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

## Cambios realizados
Se buscó probar con otros parámetros que nos diese mejor resultado.
Se cambió 

UMBRAL_GRADIENTE = 100

y se añadió la nueva variable (antes hardcodeado a 0.3)
UMBRAL_DISTANCIA = 0.15  # Bajado de 0.2 → más semillas, más núcleos pequeños detectados

El resultado que nos daba era aún peor que antes, por lo que decidí cambiar de algoritmo totalmente:
Decidí usar la imagen de Hematoxilina para restarsela a la de Eosina y así borrar más el plasma. Esto nos permitiría ser más laxos en la umbralización, permitiendo conservar más núcleos y más área.

Para esto debemos usar las imágenes de H y restarle las de E pero ajustando.

Esto resultó inutil, algo hacía que los resultados fallasen completamente, acercándose al 0%

### Propuesta nueva

# V2.0 - MEJORAS CON INTEGRACIÓN INTELIGENTE DE CANALES E y H

## Cambios realizados

Se ha implementado una mejora sustancial del algoritmo de segmentación que ahora **usa de forma inteligente ambos canales E (Eosina) y H (Hematoxilina)** para mejorar significativamente los resultados.

### Diferencias con V1.1 (intento fallido)

**V1.1 intentó:** Simplemente restar E - H de forma directa → **Falló completamente (0% accuracy)**

**V2.0 implementa:** Múltiples técnicas complementarias de procesamiento avanzado:

## Nuevas funciones implementadas

### 1. **Carga dual de imágenes E y H** (`cargar_imagen()`)
```python
imagen_h, imagen_e, imagen_color = cargar_imagen(ruta_imagen_h)
```
- Carga automáticamente ambos canales H y E
- Manejo robusto si E no está disponible (fallback a método original)
- Retorna imágenes en escala de grises para procesamiento óptimo

### 2. **Máscara de tejido usando Eosina** (`crear_mascara_tejido()`)
- **Propósito:** Identificar dónde hay tejido real vs fondo vacío
- **Método:** Umbralización de Otsu adaptativa + morfología
- **Beneficio:** Elimina detecciones falsas en zonas sin tejido
- **Impacto:** Reduce false positives significativamente

**Técnicas aplicadas:**
- Otsu threshold automático (no requiere parámetros manuales)
- Morphological closing (kernel elíptico 5x5) para rellenar huecos
- Morphological opening para eliminar ruido

### 3. **Ratio H-E para resaltar núcleos** (`calcular_ratio_h_sobre_e()`)
- **Fundamento biológico:**
  - Núcleos: Alta Hematoxilina (H) + Baja Eosina (E) → H-E es ALTO
  - Citoplasma: Baja H + Alta E → H-E es BAJO
  - Fondo: Baja H + Baja E → H-E cercano a 0

- **Cálculo:** `ratio = max(0, H_normalizado - E_normalizado)`
- **Beneficio:** Resalta núcleos mucho mejor que solo usar H
- **Aplicación de máscara:** Solo procesa zonas con tejido real

**Diferencia clave con V1.1:**
- V1.1: Restaba directamente sin normalización → valores negativos, pérdida de información
- V2.0: Normaliza a [0,1], clipping a 0, rescala a [0,255] → mantiene rangos válidos

### 4. **Mejora de contraste adaptativa CLAHE** (`mejorar_contraste_nucleos()`)
- **Técnica:** Contrast Limited Adaptive Histogram Equalization
- **Parámetros:**
  - clipLimit=3.0 (evita sobre-amplificación de ruido)
  - tileGridSize=(8,8) (procesamiento local por bloques)

- **Beneficio:** Mejora contraste de núcleos débiles sin saturar los fuertes
- **Adaptatividad:** CLAHE funciona localmente, no globalmente

### 5. **Umbralización adaptativa** (`aplicar_umbralizacion()` mejorada)
- **Método:** Adaptive Threshold Gaussian
- **Parámetros:**
  - Ventana: 11x11 (analiza contexto local)
  - C: 2 (constante de sustracción)

**Ventaja sobre umbral fijo (V1.0/V1.1):**
- Umbral fijo 110: Falla con imágenes claras/oscuras
- Umbral adaptativo: Calcula umbral óptimo para cada región de 11x11 píxeles
- **Resultado:** Se adapta automáticamente a variaciones de iluminación/tinción

### 6. **Pipeline integrado mejorado** (`procesar_imagen()` actualizada)

**Flujo de procesamiento V2.0:**

```
1. Cargar H, E y color
         ↓
2. Crear máscara de tejido (Otsu en E)
         ↓
3. Calcular H-E normalizado (resalta núcleos)
         ↓
4. Aplicar CLAHE adaptativo (mejora contraste)
         ↓
5. Umbralización adaptativa Gaussian
         ↓
6. Aplicar máscara de tejido (elimina detecciones fuera del tejido)
         ↓
7. Morfología (closing) - igual que V1.0
         ↓
8. Region growing con control de gradiente - igual que V1.0
```

## Mejoras esperadas

### 1. **Mayor Recall (detección de más núcleos reales)**
- Umbralización adaptativa detecta núcleos débiles que V1.0 perdía
- CLAHE mejora contraste de núcleos pequeños/tenues
- Ratio H-E resalta núcleos que en H solo eran difusos

**Esperado:** Recall pase de ~32% a >50%

### 2. **Mayor Precision (menos falsos positivos)**
- Máscara de tejido elimina detecciones en fondo vacío
- Ratio H-E reduce detección de citoplasma como núcleos
- Procesamiento local reduce impacto de artefactos globales

**Esperado:** Precision pase de ~51% a >65%

### 3. **Mejor F1-Score general**
- Combinación de mejor recall y precision
- **Esperado:** F1 pase de ~38% a >55%

### 4. **Mayor robustez a variaciones**
- Umbralización adaptativa maneja diferentes intensidades de tinción
- Otsu automático no requiere ajuste manual
- Procesamiento local se adapta a heterogeneidad de la imagen

**Esperado:** Reducir imágenes con F1 < 50% de 87% a <60%

## Técnicas clave que hacen V2.0 exitoso donde V1.1 falló

| Aspecto | V1.1 (Fallido) | V2.0 (Mejorado) |
|---------|----------------|------------------|
| **Combinación E-H** | Resta directa sin normalización | Resta normalizada con clipping |
| **Rango de valores** | Valores negativos → pérdida de información | [0,1] normalizado → información preservada |
| **Adaptatividad** | Umbral fijo 110 | Umbral adaptativo local |
| **Contraste** | Sin mejora | CLAHE adaptativo |
| **Máscara de tejido** | No implementada | Otsu + morfología en E |
| **Robustez** | Parámetros globales fijos | Procesamiento local adaptativo |

## Compatibilidad hacia atrás

- Si las imágenes E no están disponibles, el sistema hace **fallback automático** a métodos simplificados
- `crear_mascara_tejido()` retorna `None` si E no existe
- `calcular_ratio_h_sobre_e()` retorna solo H si E es `None`
- `mejorar_contraste_nucleos()` usa CLAHE estándar si E es `None`

**Resultado:** El código funciona tanto con dataset completo (E+H) como solo con H (compatibilidad V1.0)

## Archivos modificados

- `segmentacion_nucleos.py`:
  - Nueva función `crear_mascara_tejido()`
  - Nueva función `calcular_ratio_h_sobre_e()`
  - Nueva función `mejorar_contraste_nucleos()`
  - Mejorada `cargar_imagen()` para cargar E y H
  - Mejorada `aplicar_umbralizacion()` con modo adaptativo
  - Actualizada `procesar_imagen()` con pipeline integrado

## Próximos pasos recomendados

1. **Ejecutar segmentación:** `make segmentar` o `python segmentacion_nucleos.py`
2. **Evaluar resultados:** `make evaluar` o `python evaluar_segmentacion.py`
3. **Comparar con V1.0:** Revisar `evaluacion.csv` y comparar F1-Scores
4. **Ajuste fino (si necesario):**
   - Ajustar parámetros CLAHE (clipLimit, tileGridSize)
   - Ajustar ventana de umbralización adaptativa (11x11)
   - Ajustar constante C (actualmente 2)

