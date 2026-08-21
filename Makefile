##############################################################################
# Qwen3.8-27B — stack vLLM (servidor systemd + playground + LiteLLM)
# Uso: make help
#
# Stack:
#   - servidor: vLLM TP=2 + DFlash2 via systemd (qwen38-27b, porta 18020)
#   - playground: container docker vllm-playground (UI em :7860, network host)
#   - LiteLLM: proxy OpenAI em :4000 (docker compose em infra/litellm)
##############################################################################

PROJECT_ROOT := $(shell pwd)
# sudo só quando não-root (em container root, fica vazio)
SUDO         := $(shell [ "$$(id -u)" = "0" ] && echo "" || echo sudo)

# ── Servidor systemd ─────────────────────────────────────────────────────────
SERVICE_NAME ?= qwen38-27b
SERVICE_UNIT ?= $(PROJECT_ROOT)/infra/qwen38-27b.service
SERVICE_DEST ?= /etc/systemd/system/$(SERVICE_NAME).service
LOG          ?= $(PROJECT_ROOT)/data/logs/qwen38-27b.log
PORT         ?= 18020

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
        test \
        setup setup-repo setup-venv setup-model setup-quant setup-patches \
        setup-fast setup-dflash2 setup-service setup-verify

##############################################################################
# SERVIDOR (systemd qwen38-27b)
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

# O unit usa StandardOutput=append:data/logs/qwen38-27b.log — o journal mostra
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
	@test -x "$(PROJECT_ROOT)/qwen38-27b-rtx3090/single-user/start_qwen.sh" \
		&& echo "  ✓ qwen38-27b-rtx3090/single-user/start_qwen.sh (executável)" \
		|| { echo "  ✗ qwen38-27b-rtx3090/single-user/start_qwen.sh ausente ou sem permissão de execução"; exit 1; }
	@test -f "$(PROJECT_ROOT)/qwen38-27b-rtx3090/models/Qwen3.8-27B-DFlash2-W4A16/model.safetensors" \
		&& echo "  ✓ Drafter Qwen3.8-27B-DFlash2-W4A16 presente" \
		|| { echo "  ✗ Drafter Qwen3.8-27B-DFlash2-W4A16 ausente"; exit 1; }
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

##############################################################################
# SETUP (pipeline completo: clonar repo → venv → modelo → patches → service)
##############################################################################
# Sentinelas para cada etapa (idempotente — só roda uma vez)
_VENV_SENTINEL  := $(PROJECT_ROOT)/qwen38-27b-rtx3090/venv/bin/python
_MODEL_SENTINEL := $(PROJECT_ROOT)/qwen38-27b-rtx3090/models/Qwen3.8-27B-W4A16-AutoRound/config.json
_PATCH_SENTINEL := $(PROJECT_ROOT)/qwen38-27b-rtx3090/.patches-applied
_REPO_URL      ?= https://github.com/syv-ai/qwen38-27b-rtx3090.git

# make setup — pipeline completo, idempotente
setup: setup-repo setup-venv setup-model setup-quant setup-patches setup-fast setup-dflash2 setup-service setup-verify
	@echo ""
	@echo "  ✓ Setup completo! Para iniciar: make start"
	@echo ""

# 1. Clonar o repo (se ainda não existe)
setup-repo:
	@if [ -d "$(PROJECT_ROOT)/qwen38-27b-rtx3090/.git" ]; then \
		echo "  ✓ Repo qwen38-27b-rtx3090 já existe, pulando clone"; \
	else \
		echo "  → Clonando $(_REPO_URL)..."; \
		git clone "$(_REPO_URL)" "$(PROJECT_ROOT)/qwen38-27b-rtx3090"; \
	fi

# 2. Criar venv + instalar dependências (vllm, hf_transfer, etc.)
setup-venv:
	@if [ -f "$(_VENV_SENTINEL)" ]; then \
		echo "  ✓ venv já existe, pulando"; \
	else \
		echo "  → Criando venv..."; \
		python3 -m venv "$(PROJECT_ROOT)/qwen38-27b-rtx3090/venv"; \
		echo "  → Instalando dependências (vllm, huggingface_hub, hf_transfer)..."; \
		HF_HUB_ENABLE_HF_TRANSFER=1 "$(PROJECT_ROOT)/qwen38-27b-rtx3090/venv/bin/pip" install \
			vllm huggingface_hub hf_transfer ninja 2>&1 | tail -5; \
	fi

# 3. Baixar o modelo (~19.5 GB)
setup-model:
	@if [ -f "$(_MODEL_SENTINEL)" ]; then \
		echo "  ✓ Modelo Qwen3.8-27B-W4A16-AutoRound já baixado, pulando"; \
	else \
		echo "  → Baixando modelo (~19.5 GB)..."; \
		HF_HUB_ENABLE_HF_TRANSFER=1 "$(PROJECT_ROOT)/qwen38-27b-rtx3090/venv/bin/hf" download \
			dbirks/Qwen3.8-27B-W4A16-AutoRound \
			--local-dir "$(PROJECT_ROOT)/qwen38-27b-rtx3090/models/Qwen3.8-27B-W4A16-AutoRound"; \
	fi

# 4. Requantizar (lm_head + embed + MTP) — CPU apenas, alguns minutos
setup-quant: setup-model
	@cd "$(PROJECT_ROOT)/qwen38-27b-rtx3090" && \
		vst=$$(venv/bin/python -c "import json; w=json.load(open('models/Qwen3.8-27B-W4A16-AutoRound/model.safetensors.index.json'))['weight_map']; print('yes' if 'lm_head.weight_packed' in w and 'mtp.layers.0.mlp.down_proj.weight_packed' in w else 'no')"); \
		if [ "$$vst" = "yes" ]; then \
			echo "  ✓ Requantização já aplicada, pulando"; \
		else \
			echo "  → Requantizando lm_head, embed_tokens e MTP..."; \
			venv/bin/python quant_lm_head.py models/Qwen3.8-27B-W4A16-AutoRound && \
			venv/bin/python quant_embed.py   models/Qwen3.8-27B-W4A16-AutoRound && \
			venv/bin/python quant_mtp.py     models/Qwen3.8-27B-W4A16-AutoRound && \
			venv/bin/python build_draft_vocab.py models/Qwen3.8-27B-W4A16-AutoRound --ids draft_vocab_ids.json; \
			echo "  ✓ Requantização concluída"; \
		fi

# 5. Aplicar patches do vLLM (todos de uma vez)
setup-patches: setup-venv
	@if [ -f "$(_PATCH_SENTINEL)" ]; then \
		echo "  ✓ Patches já aplicados, pulando"; \
	else \
		echo "  → Aplicando patches do vLLM..."; \
		cd "$(PROJECT_ROOT)/qwen38-27b-rtx3090" && \
		for p in patches/*.patch; do \
			patch -p1 -d venv/lib/python3.12/site-packages/vllm < "$$p" 2>&1 | tail -1; \
		done; \
		touch "$(_PATCH_SENTINEL)"; \
	fi

# 6. Baixar variante fast (~1 GB, hardlinks do modelo base)
setup-fast: setup-venv setup-model
	@if [ -d "$(PROJECT_ROOT)/qwen38-27b-rtx3090/models/Qwen3.8-27B-W4A16-AutoRound-fast" ]; then \
		echo "  ✓ Variante fast já existe, pulando"; \
	else \
		echo "  → Baixando variante fast (int4-GPTQ lm_head)..."; \
		cd "$(PROJECT_ROOT)/qwen38-27b-rtx3090" && venv/bin/python fetch_fast_variant.py; \
	fi

# 7. Baixar drafter DFlash2 (~1.2 GB) — opcional, para SPEC=dflash2
setup-dflash2: setup-venv
	@if [ -f "$(PROJECT_ROOT)/qwen38-27b-rtx3090/models/Qwen3.8-27B-DFlash2-W4A16/model.safetensors" ]; then \
		echo "  ✓ Drafter DFlash2 já existe, pulando"; \
	else \
		echo "  → Baixando drafter DFlash2 (W4A16, ~1.2 GB)..."; \
		cd "$(PROJECT_ROOT)/qwen38-27b-rtx3090" && venv/bin/python fetch_dflash2.py; \
	fi

# 8. Instalar o unit no systemd
setup-service:
	@echo "  → Instalando serviço systemd..."
	@$(MAKE) install-service

# 9. Rodar verificação final
setup-verify:
	@echo "  → Rodando verificação..."
	@cd "$(PROJECT_ROOT)/qwen38-27b-rtx3090" && \
		VLLM_API_KEY=placeholder bash verify.sh --no-server

##############################################################################
# HELP (atualizado)
##############################################################################
help:
	@echo ""
	@echo "  Qwen3.8-27B — stack vLLM (servidor systemd + playground + LiteLLM)"
	@echo ""
	@echo "  SETUP (pipeline completo):"
	@echo "  make setup              Configura tudo: clonar repo → venv → modelo → patches → service"
	@echo ""
	@echo "  SERVIDOR (systemd qwen38-27b, TP=2 + DFlash2, porta 18020):"
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
	@echo "  API: http://localhost:18020/v1  |  Log do vLLM: $(LOG)"
	@echo ""
