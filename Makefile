##############################################################################
# Qwen3.6-27B INT4 AutoRound — vLLM Engine
# Uso: make start-bg  →  sobe servidor em background
##############################################################################

PROJECT_ROOT := $(shell pwd)
VENV         := $(PROJECT_ROOT)/.venv-vllm
PYTHON       := $(VENV)/bin/python
PIP          := $(VENV)/bin/pip
LOG          := $(PROJECT_ROOT)/data/logs/vllm.log

# Lê variáveis do .env (se existir) para usar no Makefile
-include .env
export

# Derivados do .env com fallbacks
MODEL_PATH     ?= $(PROJECT_ROOT)/data/models-vllm/Qwen3.6-27B-int4-AutoRound
SERVED_NAME    ?= qwen3
PORT           ?= 8000
MAX_MODEL_LEN  ?= 57344
KV_CACHE_DTYPE ?= fp8_e5m2
GPU_MEM_UTIL   ?= 0.97

# Serviço systemd (portável — instala/remove via make)
SERVICE_NAME   ?= qwen-vllm
SERVICE_DEST   ?= /etc/systemd/system/$(SERVICE_NAME).service
LOGROTATE_DEST ?= /etc/logrotate.d/qwen-logs
SUDO           := $(shell [ "$$(id -u)" = "0" ] && echo "" || echo sudo)
CAPTURE_MAX_MB ?= 500

.DEFAULT_GOAL := help

.PHONY: help \
        start start-bg start-text-only stop restart status logs \
        test benchmark benchmark-sweep \
        litellm-start \
        install-service uninstall-service enable-service disable-service \
        start-service stop-service service-status service-logs \
        capture-on capture-off capture-report clean-capture \
        install-logrotate uninstall-logrotate \
        clean clean-logs cron-clean-logs cron-remove-clean-logs \
        update-template \
        check _check-ready

##############################################################################
# HELP
##############################################################################
help:
	@echo ""
	@echo "  Qwen3.6-27B INT4 AutoRound — vLLM Engine"
	@echo ""
	@echo "  SERVIDOR:"
	@echo "  make start              Sobe vLLM em foreground (Ctrl+C para parar)"
	@echo "  make start-bg           Sobe em background (log: data/logs/vllm.log)"
	@echo "  make start-text-only    Sobe com --language-model-only (sem vision tower)"
	@echo "  make stop               Mata vLLM"
	@echo "  make restart            Para e sobe em background"
	@echo "  make status             Mostra estado e VRAM"
	@echo "  make logs               Acompanha log em tempo real"
	@echo ""
	@echo "  TESTES / BENCHMARK:"
	@echo "  make test               Roda suite de 13 testes (test_api.py)"
	@echo "  make benchmark          Roda bench_decode.py"
	@echo "  make benchmark ARGS=\"--start 16384 --step 16384\"  (custom)"
	@echo ""
	@echo "  LITELLM:"
	@echo "  make litellm-start      Sobe LiteLLM proxy (porta 4000)"
	@echo "  (config: infra/litellm/config.yaml)"
	@echo ""
	@echo "  SERVIÇO systemd (portátil — instala/remove em qualquer VM):"
	@echo "  make install-service    Instala o serviço (resolve caminho do repo)"
	@echo "  make enable-service     Habilita no boot + inicia (Restart=always)"
	@echo "  make disable-service    Desabilita no boot (mantém instalado)"
	@echo "  make start-service / stop-service   Inicia / para agora"
	@echo "  make service-status / service-logs  Estado / logs (journalctl)"
	@echo "  make uninstall-service  Remove o serviço"
	@echo ""
	@echo "  CAPTURA DE CONTEÚDO (debug):"
	@echo "  make capture-on         Liga log de debug + monitor de tamanho"
	@echo "  make capture-off        Desliga captura e mata o monitor"
	@echo "  make capture-report     Analisa logs do vLLM (flags, erros, timings)"
	@echo "  make clean-capture      Remove data/logs/capture"
	@echo ""
	@echo "  LOGROTATE:"
	@echo "  make install-logrotate  Instala rotação diária de logs"
	@echo "  make uninstall-logrotate Remove rotação"
	@echo ""
	@echo "  LIMPEZA:"
	@echo "  make clean              Remove logs e venv (mantém código/modelo)"
	@echo "  make clean-logs         Remove logs com mais de N dias"
	@echo "  make cron-clean-logs    Instala cron diário de limpeza"
	@echo "  make cron-remove-clean-logs  Remove o cron"
	@echo ""
	@echo "  TEMPLATE:"
	@echo "  make update-template    Baixa template froggeric mais recente"
	@echo ""
	@echo "  UTILITÁRIOS:"
	@echo "  make check              Verifica venv, modelo, GPU"
	@echo ""
	@echo "  API: http://localhost:8000/v1  |  Modelo: $(SERVED_NAME)"
	@echo ""

##############################################################################
# SERVIDOR
##############################################################################
start: _check-ready
	bash "$(PROJECT_ROOT)/scripts/start-vllm.sh"

start-bg: _check-ready
	@mkdir -p "$(PROJECT_ROOT)/data/logs"
	@pkill -f 'vllm serve' 2>/dev/null && echo "vLLM anterior parado." || true
	@sleep 2
	@nohup bash "$(PROJECT_ROOT)/scripts/start-vllm.sh" > "$(LOG)" 2>&1 &
	@echo "vLLM iniciado em background. Acompanhe: make logs"
	@echo "Aguardando ~30s para carregar..."
	@sleep 30
	@curl -sf http://localhost:$(PORT)/health > /dev/null 2>&1 && \
		echo "✓ vLLM pronto em http://localhost:$(PORT)/v1" || \
		echo "⏳ vLLM ainda carregando — aguarde mais 60s ou veja: make logs"

start-text-only: _check-ready
	@mkdir -p "$(PROJECT_ROOT)/data/logs"
	@pkill -f 'vllm serve' 2>/dev/null && echo "vLLM anterior parado." || true
	@sleep 2
	@nohup bash "$(PROJECT_ROOT)/scripts/start-vllm.sh" --language-model-only > "$(LOG)" 2>&1 &
	@echo "vLLM (text-only) iniciado em background. Acompanhe: make logs"
	@echo "Aguardando ~30s para carregar..."
	@sleep 30
	@curl -sf http://localhost:$(PORT)/health > /dev/null 2>&1 && \
		echo "✓ vLLM pronto (text-only, sem vision tower)" || \
		echo "⏳ vLLM ainda carregando — aguarde mais 60s ou veja: make logs"

stop:
	@pkill -f 'vllm serve' 2>/dev/null && echo "vLLM parado." || echo "Nenhum vLLM rodando."
	@sleep 2
	@nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader 2>/dev/null | \
		awk '{print "GPU: "$$0}'

restart: stop
	@$(MAKE) start-bg

status:
	@if curl -sf http://localhost:$(PORT)/health > /dev/null 2>&1; then \
		echo "Servidor: RODANDO em http://localhost:$(PORT)/v1 (modelo: $(SERVED_NAME))"; \
		nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader 2>/dev/null | awk '{print "GPU:     "$$0}'; \
	else \
		echo "Servidor: PARADO"; \
	fi

logs:
	@mkdir -p "$(PROJECT_ROOT)/data/logs"
	@tail -f "$(LOG)"

##############################################################################
# TESTES / BENCHMARK
##############################################################################
test:
	@$(PYTHON) "$(PROJECT_ROOT)/tests/test_api.py"

benchmark: _check-ready
	@$(PYTHON) "$(PROJECT_ROOT)/tests/bench_decode.py" $(ARGS)

benchmark-sweep: _check-ready
	@$(PYTHON) "$(PROJECT_ROOT)/tests/bench_decode.py" $(ARGS)

##############################################################################
# LITELLM
##############################################################################
litellm-start:
	@if ! $(PIP) show litellm > /dev/null 2>&1; then \
		echo "Instalando litellm..."; \
		$(PIP) install --quiet litellm; \
	fi
	@echo "Subindo LiteLLM proxy em http://localhost:4000 ..."
	@echo "  config: infra/litellm/config.yaml"
	@echo "  use model_name=qwen nos seus projetos"
	@echo ""
	$(VENV)/bin/litellm --config "$(PROJECT_ROOT)/infra/litellm/config.yaml" --port 4000

##############################################################################
# SERVIÇO SYSTEMD
##############################################################################
install-service:
	@chmod +x "$(PROJECT_ROOT)/scripts/start-vllm.sh"
	@mkdir -p "$(PROJECT_ROOT)/data/logs"
	@sed "s|__PROJECT_ROOT__|$(PROJECT_ROOT)|g" \
		"$(PROJECT_ROOT)/infra/vllm/qwen-vllm.service" \
		| $(SUDO) tee "$(SERVICE_DEST)" > /dev/null
	@$(SUDO) systemctl daemon-reload
	@echo "✓ Serviço '$(SERVICE_NAME)' instalado em $(SERVICE_DEST)"
	@echo "  make enable-service    → auto-start no boot + Restart=always"
	@echo "  make start-service     → inicia agora sem habilitar no boot"

uninstall-service:
	@$(SUDO) systemctl disable --now $(SERVICE_NAME) 2>/dev/null || true
	@$(SUDO) rm -f "$(SERVICE_DEST)"
	@$(SUDO) systemctl daemon-reload
	@echo "✓ Serviço '$(SERVICE_NAME)' removido."

enable-service:
	@$(SUDO) systemctl enable --now $(SERVICE_NAME)
	@echo "✓ Serviço habilitado (auto-start no boot) e iniciado."
	@echo "  Estado: make service-status   Logs: make service-logs"

disable-service:
	@$(SUDO) systemctl disable --now $(SERVICE_NAME) 2>/dev/null || true
	@echo "✓ Serviço desabilitado — não inicia mais no boot."

start-service:
	@$(SUDO) systemctl start $(SERVICE_NAME)
	@echo "✓ Serviço iniciado."

stop-service:
	@$(SUDO) systemctl stop $(SERVICE_NAME) 2>/dev/null || true
	@echo "✓ Serviço parado."

service-status:
	@$(SUDO) systemctl status $(SERVICE_NAME) --no-pager || true

service-logs:
	@$(SUDO) journalctl -u $(SERVICE_NAME) -f --no-pager

##############################################################################
# CAPTURA DE CONTEÚDO (debug)
##############################################################################
capture-on:
	@grep -q '^CAPTURE_LOG=' "$(PROJECT_ROOT)/.env" 2>/dev/null \
		&& sed -i 's/^CAPTURE_LOG=.*/CAPTURE_LOG=true/' "$(PROJECT_ROOT)/.env" \
		|| echo 'CAPTURE_LOG=true' >> "$(PROJECT_ROOT)/.env"
	@echo "✓ CAPTURE_LOG=true — reiniciando p/ ligar a captura..."
	@$(MAKE) _capture-restart
	@mkdir -p "$(PROJECT_ROOT)/data/logs/capture"
	@if [ -f "$(PROJECT_ROOT)/data/logs/capture/monitor.pid" ] && kill -0 $$(cat "$(PROJECT_ROOT)/data/logs/capture/monitor.pid") 2>/dev/null; then \
		echo "  Monitor de tamanho ja rodando (PID $$(cat "$(PROJECT_ROOT)/data/logs/capture/monitor.pid"))."; \
	else \
		nohup "$(PROJECT_ROOT)/scripts/capture-size-monitor.sh" >/dev/null 2>&1 & \
		echo "  Monitor de tamanho iniciado (limite: $${CAPTURE_MAX_MB:-500}MB, intervalo: 30min)."; \
	fi
	@echo "  Reproduza o problema e rode:  make capture-report"

capture-off:
	@if [ -f "$(PROJECT_ROOT)/data/logs/capture/monitor.pid" ]; then \
		PID=$$(cat "$(PROJECT_ROOT)/data/logs/capture/monitor.pid"); \
		if kill -0 "$$PID" 2>/dev/null; then \
			kill -9 "$$PID" 2>/dev/null && echo "✓ Monitor de tamanho parado (PID $$PID)."; \
		fi; \
		rm -f "$(PROJECT_ROOT)/data/logs/capture/monitor.pid"; \
	fi
	@grep -q '^CAPTURE_LOG=' "$(PROJECT_ROOT)/.env" 2>/dev/null \
		&& sed -i 's/^CAPTURE_LOG=.*/CAPTURE_LOG=false/' "$(PROJECT_ROOT)/.env" || true
	@echo "✓ CAPTURE_LOG=false — reiniciando p/ desligar a captura..."
	@$(MAKE) _capture-restart

capture-report:
	@$(PYTHON) "$(PROJECT_ROOT)/scripts/analyze-capture.py" $(ARGS)

clean-capture:
	@rm -rf "$(PROJECT_ROOT)/data/logs/capture"
	@echo "✓ Captura limpa (data/logs/capture removido)."

_capture-restart:
	@if systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		echo "Reiniciando via systemd ($(SERVICE_NAME))..."; $(SUDO) systemctl restart $(SERVICE_NAME); \
	else \
		echo "Reiniciando via make restart..."; $(MAKE) restart; \
	fi

##############################################################################
# LOGROTATE
##############################################################################
install-logrotate:
	@sed "s|__PROJECT_ROOT__|$(PROJECT_ROOT)|g" \
		"$(PROJECT_ROOT)/infra/logrotate/qwen-logs" \
		| $(SUDO) tee "$(LOGROTATE_DEST)" > /dev/null
	@$(SUDO) logrotate --debug "$(LOGROTATE_DEST)" >/dev/null 2>&1 && \
		echo "✓ logrotate instalado e validado em $(LOGROTATE_DEST)." || \
		echo "✓ logrotate instalado em $(LOGROTATE_DEST) (valide: logrotate --debug $(LOGROTATE_DEST))"

uninstall-logrotate:
	@$(SUDO) rm -f "$(LOGROTATE_DEST)"
	@echo "✓ logrotate removido ($(LOGROTATE_DEST))."

##############################################################################
# LIMPEZA
##############################################################################
clean:
	@echo "Removendo logs e venv..."
	@rm -rf "$(PROJECT_ROOT)/data/logs/"* "$(VENV)"
	@echo "Código e modelo mantidos. Execute 'make check' para verificar."

clean-logs:
	@DAYS="$${LOG_RETENTION_DAYS:-7}"; \
	echo "Removendo logs com mais de $$DAYS dias em data/logs/..."; \
	cd "$(PROJECT_ROOT)/data/logs" && \
	find . -maxdepth 1 -type f -name '*.log' ! -name '.gitkeep' -mtime +$$DAYS -delete -print | \
	while read f; do echo "  removido: $$f"; done; \
	echo "Pronto."

cron-clean-logs:
	@DAYS="$${LOG_RETENTION_DAYS:-7}"; \
	CMD="cd $(PROJECT_ROOT) && make clean-logs"; \
	CRON_ID="qwen-clean-logs"; \
	(crontab -l 2>/dev/null | grep -v "$$CRON_ID") | \
	(echo "0 3 * * * $$CMD  # $$CRON_ID") | crontab -; \
	echo "Cron instalado: todo dia às 03:00 (retention=$$DAYS dias)"

cron-remove-clean-logs:
	@crontab -l 2>/dev/null | grep -v "qwen-clean-logs" | crontab - 2>/dev/null || true
	@echo "Cron de limpeza de logs removido."

##############################################################################
# TEMPLATE
##############################################################################
update-template:
	@echo "Baixando template froggeric mais recente..."
	@mkdir -p "$(PROJECT_ROOT)/data/templates/custom"
	@TMPFILE=$$(mktemp); \
	URL="https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates/resolve/main/chat_template.jinja"; \
	if curl -sL --fail "$$URL" -o "$$TMPFILE" 2>/dev/null; then \
		VERSION=$$(grep -oP 'template_version\s*=\s*"\K[^"]+' "$$TMPFILE" 2>/dev/null || echo "unknown"); \
		echo "  Versão baixada: $$VERSION"; \
		if [ -f "$(PROJECT_ROOT)/data/templates/custom/chat_template_local.jinja" ]; then \
			cp "$(PROJECT_ROOT)/data/templates/custom/chat_template_local.jinja" \
				"$(PROJECT_ROOT)/data/templates/custom/chat_template_local.jinja.bak" 2>/dev/null || true; \
		fi; \
		cp "$$TMPFILE" "$(PROJECT_ROOT)/data/templates/custom/chat_template_v21.jinja"; \
		echo "  ✓ Pristine salvo em custom/chat_template_v21.jinja"; \
		if [ -f "$(PROJECT_ROOT)/data/templates/custom/chat_template_local.jinja" ]; then \
			echo ""; \
			echo "  ATENÇÃO: chat_template_local.jinja (ativo) NÃO foi alterado."; \
			echo "  Para ver diferenças com a nova versão:"; \
			echo "    diff data/templates/custom/chat_template_v21.jinja \\"; \
			echo "         data/templates/custom/chat_template_local.jinja"; \
			echo "  E mescle as mudanças manualmente em chat_template_local.jinja."; \
		fi; \
	else \
		echo "  ERRO: não foi possível baixar template de $$URL"; \
		rm -f "$$TMPFILE"; \
		exit 1; \
	fi; \
	rm -f "$$TMPFILE"

##############################################################################
# UTILITÁRIOS
##############################################################################
check:
	@echo "Verificando ambiente..."
	@# venv
	@test -f "$(VENV)/bin/python" && echo "  ✓ venv: $(VENV)" || \
		echo "  ✗ venv não encontrado — crie com: python3 -m venv $(VENV) && $(VENV)/bin/pip install openai requests"
	@# modelo
	@test -d "$(MODEL_PATH)" && echo "  ✓ modelo: $(MODEL_PATH)" || \
		echo "  ✗ modelo não encontrado em $(MODEL_PATH)"
	@# GPU
	@nvidia-smi --query-gpu=name,memory.free --format=csv,noheader 2>/dev/null | \
		awk '{print "  ✓ GPU: "$$0}' || echo "  ✗ nvidia-smi não encontrado"
	@# vLLM
	@if curl -sf http://localhost:$(PORT)/health > /dev/null 2>&1; then \
		echo "  ✓ vLLM: RODANDO em :$(PORT)"; \
	else \
		echo "  ○ vLLM: parado (make start-bg para iniciar)"; \
	fi

_check-ready:
	@test -f "$(VENV)/bin/python" || \
		(echo "ERRO: venv não encontrado em $(VENV). Crie com:"; \
		 echo "  python3 -m venv $(VENV) && $(VENV)/bin/pip install openai requests"; \
		 exit 1)
	@test -d "$(MODEL_PATH)" || \
		(echo "ERRO: modelo não encontrado em $(MODEL_PATH)"; exit 1)
