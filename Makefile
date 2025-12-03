.PHONY: all segmentar evaluar visualizar limpiar reiniciar

all: segmentar evaluar visualizar

segmentar:
	@.venv/bin/python segmentar.py

evaluar:
	@.venv/bin/python evaluar.py

visualizar:
	@.venv/bin/python visualizar.py

limpiar:
	@rm -rf out visualizaciones
	@rm -f resultados.csv evaluacion.csv

reiniciar: limpiar all
