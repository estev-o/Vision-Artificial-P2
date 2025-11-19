.PHONY: all segmentar evaluar visualizar limpiar reiniciar

all: segmentar evaluar

segmentar:
	@.venv/bin/python segmentacion_nucleos.py

evaluar:
	@.venv/bin/python evaluar_pixel_a_pixel.py

visualizar:
	@.venv/bin/python generar_visualizaciones.py

limpiar:
	@rm -rf out visualizaciones
	@mkdir -p out
	@rm -f resultados.csv evaluacion.csv

reiniciar: limpiar all
