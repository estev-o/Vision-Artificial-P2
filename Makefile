.PHONY: all segmentar evaluar limpiar reiniciar

all: segmentar evaluar

segmentar:
	@.venv/bin/python segmentacion_nucleos.py

evaluar:
	@.venv/bin/python evaluar_pixel_a_pixel.py

limpiar:
	@rm -rf out
	@mkdir -p out
	@rm -f resultados.csv evaluacion.csv

reiniciar: limpiar all
