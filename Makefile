PROJECT_ROOT := $(shell pwd)
VENV         := $(PROJECT_ROOT)/.venv
PYTHON       := $(VENV)/bin/python
LOG          := $(PROJECT_ROOT)/data/logs/server.log

.DEFAULT_GOAL := help

.PHONY: help setup start start-bg stop restart status logs test fix-template install-service

help:
	@echo ""
	@echo "  qwen3 — llama-cpp-python + Qwen3.6 27B GGUF"
	@echo ""
	@echo "  make setup            Instala dependencias e baixa o modelo (rodar 1x)"
	@echo "  make start            Sobe o servidor em foreground (Ctrl+C para parar)"
	@echo "  make start-bg         Sobe em background (log em data/logs/vllm.log)"
	@echo "  make stop             Para o servidor"
	@echo "  make restart          Para e sobe em background"
	@echo "  make status           Mostra se esta rodando e uso de VRAM"
	@echo "  make logs             Acompanha o log em tempo real"
	@echo "  make test             Roda a suite de testes da API"
	@echo "  make fix-template     Aplica o template froggeric no tokenizer"
	@echo "  make install-service  Instala e ativa como servico systemd (boot automatico)"
	@echo ""
	@echo "  API OpenAI-compatible:"
	@echo "    Base URL : http://localhost:8000/v1"
	@echo "    Modelo   : qwen3"
	@echo ""

setup:
	bash $(PROJECT_ROOT)/scripts/setup.sh

start:
	bash $(PROJECT_ROOT)/scripts/start-server.sh

start-bg:
	@mkdir -p $(PROJECT_ROOT)/data/logs
	@bash $(PROJECT_ROOT)/scripts/start-server.sh >> $(LOG) 2>&1 &
	@echo "Servidor iniciado em background. Acompanhe: make logs"

stop:
	@pkill -f "llama_cpp.server" 2>/dev/null && echo "Servidor parado." || echo "Nenhum servidor rodando."

restart: stop
	@sleep 2
	@$(MAKE) start-bg

status:
	@if curl -sf http://localhost:8000/health > /dev/null 2>&1; then \
		echo "Servidor: RODANDO em http://localhost:8000/v1"; \
		nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader 2>/dev/null | awk '{print "GPU:     "$$0}'; \
	else \
		echo "Servidor: PARADO"; \
	fi

logs:
	@mkdir -p $(PROJECT_ROOT)/data/logs
	tail -f $(LOG)

test:
	@$(PYTHON) $(PROJECT_ROOT)/tests/test_api.py

fix-template:
	@$(PYTHON) $(PROJECT_ROOT)/src/fix_template.py

install-service:
	@sudo cp $(PROJECT_ROOT)/infra/qwen-server.service /etc/systemd/system/
	@sudo systemctl daemon-reload
	@sudo systemctl enable qwen-server
	@sudo systemctl start qwen-server
	@echo "Servico instalado e iniciado. Verifique: sudo systemctl status qwen-server"
