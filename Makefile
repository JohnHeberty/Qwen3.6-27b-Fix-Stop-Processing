##############################################################################
# Qwen3.8-27B — stack vLLM (servidor systemd + playground + LiteLLM)
# Uso: make help
#
# Stack:
#   - servidor: vLLM TP=2 + DFlash2 via systemd (qwen-vllm-dflash2, porta 8080)
#   - playground: container docker vllm-playground (UI em :7860, network host)
#   - LiteLLM: proxy OpenAI em :4000 (docker compose em infra/litellm)
##############################################################################

PROJECT_ROOT := $(shell pwd)
# sudo só quando não-root (em container root, fica vazio)
SUDO         := $(shell [ "$$(id -u)" = "0" ] && echo "" || echo sudo)

# ── Servidor systemd ─────────────────────────────────────────────────────────
SERVICE_NAME ?= qwen-vllm-dflash2
SERVICE_UNIT ?= $(PROJECT_ROOT)/infra/vllm/qwen-vllm-dflash2.service
SERVICE_DEST ?= /etc/systemd/system/$(SERVICE_NAME).service
LOG          ?= $(PROJECT_ROOT)/data/logs/vllm-dflash2.log
PORT         ?= 8080

# ── Docker compose ───────────────────────────────────────────────────────────
COMPOSE_PLAYGROUND ?= $(PROJECT_ROOT)/docker-compose.yml
COMPOSE_LITELLM    ?= $(PROJECT_ROOT)/infra/litellm/docker-compose.yml
LITELLM_ENV        ?= $(PROJECT_ROOT)/infra/litellm/.env

.DEFAULT_GOAL := help

.PHONY: help \
        start stop restart status logs \
        install-service uninstall-service \
        playground-up playground-down playground-logs playground-build \
        litellm-start litellm-stop \
        test

##############################################################################
# HELP
##############################################################################
help:
	@echo ""
	@echo "  Qwen3.8-27B — stack vLLM (servidor systemd + playground + LiteLLM)"
	@echo ""
	@echo "  SERVIDOR (systemd qwen-vllm-dflash2, TP=2 + DFlash2, porta 8080):"
	@echo "  make start              Inicia o serviço"
	@echo "  make stop               Para o serviço"
	@echo "  make restart            Reinicia o serviço"
	@echo "  make status             Estado (active/enabled) + API health + VRAM"
	@echo "  make logs               Acompanha journal do serviço (Ctrl+C)"
	@echo ""
	@echo "  INSTALAÇÃO DO SERVIÇO:"
	@echo "  make install-service    Instala unit versionado (substitui symlink quebrado)"
	@echo "  make uninstall-service  Para, desabilita e remove o unit instalado"
	@echo ""
	@echo "  PLAYGROUND (container vllm-playground, UI em :7860):"
	@echo "  make playground-up      Sobe o playground em background"
	@echo "  make playground-down    Para o playground"
	@echo "  make playground-logs    Acompanha logs do playground (Ctrl+C)"
	@echo "  make playground-build   Reconstrói a imagem do playground"
	@echo ""
	@echo "  LITELLM (proxy em :4000, exige infra/litellm/.env):"
	@echo "  make litellm-start      Sobe LiteLLM + Postgres em background"
	@echo "  make litellm-stop       Para LiteLLM + Postgres"
	@echo ""
	@echo "  VALIDAÇÃO:"
	@echo "  make test               Validação offline (paths + JSON, sem servidor)"
	@echo ""
	@echo "  API: http://localhost:8080/v1  |  Log do vLLM: $(LOG)"
	@echo ""

##############################################################################
# SERVIDOR (systemd qwen-vllm-dflash2)
##############################################################################
start:
	$(SUDO) systemctl start $(SERVICE_NAME)
	@echo "✓ Serviço iniciado. Estado: make status"

stop:
	$(SUDO) systemctl stop $(SERVICE_NAME)
	@echo "✓ Serviço parado."

restart:
	$(SUDO) systemctl restart $(SERVICE_NAME)
	@echo "✓ Serviço reiniciado. Estado: make status"

status:
	@echo "Serviço:   $$(systemctl is-active $(SERVICE_NAME) 2>/dev/null || echo 'inativo')"
	@echo "Boot:      $$(systemctl is-enabled $(SERVICE_NAME) 2>/dev/null || echo 'não habilitado')"
	@if systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		curl -sf http://localhost:$(PORT)/health >/dev/null 2>&1 \
			&& echo "API health: OK (http://localhost:$(PORT))" \
			|| echo "API health: sem resposta (serviço ativo, aguardando subir)"; \
	fi
	@nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader 2>/dev/null | awk '{print "GPU:       "$$0}'

# O unit usa StandardOutput=append:data/logs/vllm-dflash2.log — o journal mostra
# apenas o ciclo de vida do serviço; o conteúdo completo fica em $(LOG).
logs:
	@echo "Acompanhando journal do serviço $(SERVICE_NAME) (Ctrl+C para sair)..."
	@echo "Log completo do vLLM: $(LOG)"
	$(SUDO) journalctl -u $(SERVICE_NAME) -f --no-pager

##############################################################################
# INSTALAÇÃO DO SERVIÇO
##############################################################################
# Instala o unit versionado no systemd. Usa install (e NÃO cp) de propósito: o
# destino hoje é um symlink quebrado (→ /root/qwen3/systemd/, diretório
# removido) e cp seguiria o symlink e falharia; install substitui o symlink
# por um arquivo regular.
install-service:
	$(SUDO) install -m 644 "$(SERVICE_UNIT)" "$(SERVICE_DEST)"
	@$(SUDO) systemctl daemon-reload
	@$(SUDO) systemctl enable $(SERVICE_NAME)
	@echo "✓ Unit '$(SERVICE_NAME)' instalado em $(SERVICE_DEST)"
	@echo "  (substitui o symlink quebrado — unit versionado em $(SERVICE_UNIT))"
	@echo "  Inicie com: make start   |   Estado: make status"

# Para, desabilita do boot e remove o unit instalado (o unit versionado no
# repo permanece intacto).
uninstall-service:
	@$(SUDO) systemctl stop $(SERVICE_NAME) 2>/dev/null || true
	@$(SUDO) systemctl disable $(SERVICE_NAME) 2>/dev/null || true
	@$(SUDO) rm -f "$(SERVICE_DEST)"
	@$(SUDO) systemctl daemon-reload
	@echo "✓ Serviço '$(SERVICE_NAME)' removido. Unit versionado no repo permanece."

##############################################################################
# PLAYGROUND (docker compose raiz — container vllm-playground, UI em :7860)
##############################################################################
playground-up:
	@echo "Subindo playground vLLM (container 'vllm-playground', UI em :7860)..."
	docker compose -f "$(COMPOSE_PLAYGROUND)" up -d

playground-down:
	@echo "Parando playground vLLM..."
	docker compose -f "$(COMPOSE_PLAYGROUND)" down

playground-logs:
	@echo "Acompanhando logs do playground (Ctrl+C para sair)..."
	docker compose -f "$(COMPOSE_PLAYGROUND)" logs -f

playground-build:
	@echo "Construindo imagem do playground..."
	docker compose -f "$(COMPOSE_PLAYGROUND)" build

##############################################################################
# LITELLM (docker compose em infra/litellm — proxy em :4000)
##############################################################################
# O compose exige ${POSTGRES_PASSWORD:?} e env_file: .env — sem o arquivo ele
# falha de forma confusa. Checamos antes com erro claro.
litellm-start:
	@if [ ! -f "$(LITELLM_ENV)" ]; then \
		echo ""; \
		echo "  ERRO: $(LITELLM_ENV) não existe."; \
		echo "  Crie infra/litellm/.env com POSTGRES_PASSWORD (o compose exige a variável)."; \
		echo "  Exemplo:"; \
		echo "    POSTGRES_PASSWORD=<senha-forte>"; \
		echo ""; \
		exit 1; \
	fi
	@echo "Subindo LiteLLM (proxy em :4000 + Postgres)..."
	docker compose -f "$(COMPOSE_LITELLM)" up -d

litellm-stop:
	@echo "Parando LiteLLM..."
	docker compose -f "$(COMPOSE_LITELLM)" down

##############################################################################
# VALIDAÇÃO OFFLINE (não existe tests/ na raiz — roda sem servidor)
##############################################################################
# Verifica os paths críticos da stack e a integridade dos JSONs versionados.
test:
	@echo "Validando stack vLLM (offline)..."
	@test -x "$(PROJECT_ROOT)/scripts/start-vllm-dflash2.sh" \
		&& echo "  ✓ scripts/start-vllm-dflash2.sh (executável)" \
		|| { echo "  ✗ scripts/start-vllm-dflash2.sh ausente ou sem permissão de execução"; exit 1; }
	@test -f "$(SERVICE_UNIT)" \
		&& echo "  ✓ $(SERVICE_UNIT)" \
		|| { echo "  ✗ $(SERVICE_UNIT) ausente"; exit 1; }
	@test -f "$(COMPOSE_PLAYGROUND)" \
		&& echo "  ✓ $(COMPOSE_PLAYGROUND)" \
		|| { echo "  ✗ $(COMPOSE_PLAYGROUND) ausente"; exit 1; }
	@test -f "$(COMPOSE_LITELLM)" \
		&& echo "  ✓ $(COMPOSE_LITELLM)" \
		|| { echo "  ✗ $(COMPOSE_LITELLM) ausente"; exit 1; }
	@for f in opencode.json infra/opencode/config.json data/vllm-playground/instances.json; do \
		if python3 -m json.tool "$(PROJECT_ROOT)/$$f" >/dev/null 2>&1; then \
			echo "  ✓ $$f (JSON válido)"; \
		else \
			echo "  ✗ $$f (JSON inválido)"; exit 1; \
		fi; \
	done
	@echo "  ✓ Validação offline OK — stack pronta"
