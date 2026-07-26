##############################################################################
# Qwen3.6-35B-A3B — Pipeline plug-and-play zero-dependência
# Uso: make setup  →  inicia tudo do zero em qualquer máquina
##############################################################################

PROJECT_ROOT := $(shell pwd)
VENV         := $(PROJECT_ROOT)/.venv
PYTHON       := $(VENV)/bin/python
PIP          := $(VENV)/bin/pip
LOG          := $(PROJECT_ROOT)/data/logs/server.log

# Lê variáveis do .env (se existir) para usar no Makefile
-include .env
export

# Derivados do .env com fallbacks
LLAMA_CPP_DIR    ?= $(HOME)/llama.cpp
LLAMA_SERVER     ?= $(LLAMA_CPP_DIR)/build/bin/llama-server
# Commit fixado do llama.cpp — builds reproduzíveis (upstream não tem release
# estável e o HEAD de master pode quebrar patches/ABI). Para atualizar, rode:
#   LLAMA_CPP_COMMIT=<novo-sha> make update-llama-server   (e teste antes de commitar)
# Deixe vazio (LLAMA_CPP_COMMIT= make ...) para seguir o tip de master (não recomendado).
LLAMA_CPP_COMMIT ?= e8f19cc0ad70a243c8012bf17b4be601abfc8ea2

# Serviço systemd (portável — instala/remove via make, caminho resolvido no install)
SERVICE_NAME     ?= qwen-server
SERVICE_DEST     ?= /etc/systemd/system/$(SERVICE_NAME).service
LOGROTATE_DEST   ?= /etc/logrotate.d/qwen-logs
# sudo só quando não-root (em container root, fica vazio)
SUDO             := $(shell [ "$$(id -u)" = "0" ] && echo "" || echo sudo)
CUDA_HOME        ?= /usr/local/cuda
MODEL_DIR        ?= $(PROJECT_ROOT)/data/models
MODEL_FILE       ?= Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
HF_TOKEN         ?= $(HUGGINGFACE_TOKEN)

.DEFAULT_GOAL := help

# ── Sentinels (arquivos que indicam etapa concluída) ──────────────────────────
SENTINEL_VENV        := $(VENV)/bin/python
SENTINEL_LLAMA       := $(LLAMA_SERVER)
SENTINEL_LLAMACPP_PY := $(VENV)/bin/llama-server
SENTINEL_MODEL       := $(MODEL_DIR)/$(MODEL_FILE)

.PHONY: help setup \
        install-system-deps setup-cuda create-venv install-python-deps \
        build-llama-server rebuild-llama-server build-llama-cpp-python \
        update-llama-server unpatch-glibc-cuda \
        download-model \
        start start-bg stop restart status logs test \
        install-service uninstall-service enable-service disable-service \
        start-service stop-service service-status service-logs \
        configure-ollama ollama-unload \
        litellm-start \
        benchmark benchmark-sweep \
        capture-on capture-off capture-report clean-capture _capture-restart \
        install-logrotate uninstall-logrotate \
        clean clean-logs cron-clean-logs cron-remove-clean-logs

##############################################################################
# HELP
##############################################################################
help:
	@echo ""
	@echo "  Qwen3.6-35B-A3B — llama-server GGUF"
	@echo ""
	@echo "  SETUP (zero-dependência):"
	@echo "  make setup              Pipeline completa: instala tudo do zero"
	@echo "  make install-system-deps  [1] Instala Python, cmake, git, build-essential"
	@echo "  make setup-cuda           [2] Verifica / instala CUDA toolkit"
	@echo "  make create-venv          [3] Cria virtualenv Python"
	@echo "  make install-python-deps  [4] Instala gguf, huggingface-hub, etc."
	@echo "  make build-llama-server   [5] Compila llama-server com CUDA"
	@echo "  make rebuild-llama-server  Recompila do zero (remove binário + build)"
	@echo "  make update-llama-server   Atualiza llama.cpp + recompila"
	@echo "  make unpatch-glibc-cuda    Reverte patch glibc em /usr/include"
	@echo "  make build-llama-cpp-python [6] Compila llama-cpp-python com CUDA"
	@echo "  make download-model       [7] Baixa modelo GGUF do HuggingFace"
	@echo ""
	@echo "  SERVIDOR:"
	@echo "  make start              Sobe servidor em foreground (Ctrl+C para parar)"
	@echo "  make start-bg           Sobe em background"
	@echo "  make stop               Para o servidor"
	@echo "  make restart            Para e sobe em background"
	@echo "  make status             Mostra estado e VRAM"
	@echo "  make logs               Acompanha log em tempo real"
	@echo "  make test               Roda suite de testes da API"
	@echo ""
	@echo "  SERVIÇO systemd (portável — instala/remove em qualquer VM):"
	@echo "  make install-service    Instala o serviço (resolve o caminho do repo)"
	@echo "  make enable-service     Habilita no boot + inicia (Restart=always)"
	@echo "  make disable-service    Desabilita no boot (mantém instalado)"
	@echo "  make start-service / stop-service   Inicia / para agora"
	@echo "  make service-status / service-logs  Estado / logs (journalctl)"
	@echo "  make uninstall-service  Remove o serviço (código do repo fica intacto)"
	@echo ""
	@echo "  LIMPEZA:"
	@echo "  make clean              Remove modelo, logs e venv (mantém código)"
	@echo "  make clean-logs         Remove logs com mais de N dias (LOG_RETENTION_DAYS no .env)"
	@echo "  make cron-clean-logs    Instala cron diário de limpeza (usa LOG_RETENTION_DAYS)"
	@echo "  make cron-remove-clean-logs  Remove o cron de limpeza"
	@echo ""
	@echo "  CAPTURA DE CONTEÚDO (debug de tool-calling / loop):"
	@echo "  make capture-on         Liga o log de prompt+geração e reinicia"
	@echo "  make capture-off        Desliga a captura e reinicia"
	@echo "  make capture-report     Analisa a captura (flags: loop, turno-vazio, overflow)"
	@echo "  make clean-capture      Remove data/logs/capture"
	@echo ""
	@echo "  CONFLITO OLLAMA/GPU (compartilham 24 GB VRAM):"
	@echo "  make configure-ollama   Reduz OLLAMA_KEEP_ALIVE 30m → 5m"
	@echo "  make ollama-unload      Força Ollama a liberar VRAM agora"
	@echo "  (make start já descarrega Ollama automaticamente)"
	@echo ""
	@echo "  LITELLM:"
	@echo "  make litellm-start      Sobe LiteLLM proxy (porta 4000) com config pronta"
	@echo "  (config: infra/litellm/config.yaml — já inclui context_window correto)"
	@echo ""
	@echo "  BENCHMARK:"
	@echo "  make benchmark          Sweep 8k→max (incremento 8k, com MTP)"
	@echo "  make benchmark ARGS=\"--start 16384 --step 16384\"  (custom)"
	@echo ""
	@echo "  API: http://localhost:8000/v1  |  Modelo: qwen3"
	@echo ""

##############################################################################
# [0] SETUP COMPLETO — encadeia todas as etapas
##############################################################################
setup: install-system-deps setup-cuda create-venv install-python-deps \
       build-llama-server build-llama-cpp-python download-model
	@echo ""
	@echo "  ✓ Setup completo!"
	@echo "  Execute: make start"
	@echo ""

##############################################################################
# [1] DEPENDÊNCIAS DO SISTEMA
##############################################################################
install-system-deps:
	@echo "[1/8] Verificando dependências do sistema..."
	@MISSING=""; \
	command -v python3   >/dev/null 2>&1 || MISSING="$$MISSING python3 python3-venv python3-pip"; \
	command -v cmake     >/dev/null 2>&1 || MISSING="$$MISSING cmake"; \
	command -v git       >/dev/null 2>&1 || MISSING="$$MISSING git"; \
	command -v gcc       >/dev/null 2>&1 || MISSING="$$MISSING build-essential"; \
	command -v curl      >/dev/null 2>&1 || MISSING="$$MISSING curl"; \
	if [ -n "$$MISSING" ]; then \
		echo "      Instalando:$$MISSING"; \
		apt-get update -qq && apt-get install -y --no-install-recommends $$MISSING 2>/dev/null; \
	else \
		echo "      OK — python3=$$(python3 --version 2>&1 | grep -oP '\d+\.\d+\.\d+'), cmake=$$(cmake --version | head -1 | grep -oP '\d+\.\d+\.\d+')"; \
	fi

##############################################################################
# [2] CUDA TOOLKIT
##############################################################################
setup-cuda:
	@echo "[2/8] Verificando CUDA toolkit..."
	@if [ -x "$(CUDA_HOME)/bin/nvcc" ] && [ -f "$(CUDA_HOME)/lib64/libcudart.so" ]; then \
		echo "      OK — CUDA já configurado em $(CUDA_HOME)"; \
	elif command -v nvidia-smi >/dev/null 2>&1; then \
		echo "      GPU detectada: $$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"; \
		echo "      Verificando CUDA toolkit..."; \
		if dpkg -l | grep -q "cuda-toolkit" 2>/dev/null; then \
			echo "      CUDA toolkit instalado via apt — verificando nvcc..."; \
		fi; \
		if [ ! -x "$(CUDA_HOME)/bin/nvcc" ]; then \
			echo ""; \
			echo "  ERRO: CUDA toolkit não encontrado em $(CUDA_HOME)"; \
			echo "  Instale com:"; \
			echo "    wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb"; \
			echo "    dpkg -i cuda-keyring_1.1-1_all.deb"; \
			echo "    apt-get install -y cuda-toolkit-12-8"; \
			echo ""; \
			exit 1; \
		fi; \
	else \
		echo ""; \
		echo "  ERRO: nenhuma GPU NVIDIA detectada (nvidia-smi não encontrado)"; \
		echo "  Instale o driver NVIDIA primeiro: https://www.nvidia.com/drivers"; \
		echo ""; \
		exit 1; \
	fi
	@# Registrar libs CUDA no ldconfig se necessário
	@if [ -d "$(CUDA_HOME)/lib64" ] && ! ldconfig -p 2>/dev/null | grep -q "libcudart.so.12"; then \
		echo "$(CUDA_HOME)/lib64" | tee /etc/ld.so.conf.d/cuda.conf >/dev/null 2>&1; \
		ldconfig 2>/dev/null || true; \
	fi

##############################################################################
# [3] VIRTUALENV
##############################################################################
create-venv: $(SENTINEL_VENV)

$(SENTINEL_VENV):
	@echo "[3/8] Criando virtualenv..."
	@python3 -m venv "$(VENV)"
	@echo "      OK — $(VENV)"

##############################################################################
# [4] DEPENDÊNCIAS PYTHON (exceto llama-cpp-python)
##############################################################################
install-python-deps: $(SENTINEL_VENV)
	@echo "[4/8] Instalando dependências Python..."
	@$(PIP) install --quiet --upgrade pip
	@$(PIP) install --quiet gguf huggingface-hub openai requests
	@echo "      OK"

##############################################################################
# [5] COMPILAR llama-server
##############################################################################
build-llama-server: $(SENTINEL_LLAMA)

$(SENTINEL_LLAMA): setup-cuda install-system-deps
	@echo "[5/8] Compilando llama-server com CUDA..."
	@# Clonar llama.cpp se não existir
	@if [ ! -d "$(LLAMA_CPP_DIR)" ]; then \
		echo "      Clonando llama.cpp..."; \
		git clone --depth=1 https://github.com/ggml-org/llama.cpp.git "$(LLAMA_CPP_DIR)"; \
	fi
	@# Fixar no commit reproduzível (se LLAMA_CPP_COMMIT definido)
	@if [ -n "$(LLAMA_CPP_COMMIT)" ]; then \
		cd "$(LLAMA_CPP_DIR)" && \
		if ! git cat-file -e "$(LLAMA_CPP_COMMIT)^{commit}" 2>/dev/null; then \
			echo "      Buscando commit fixado $(LLAMA_CPP_COMMIT)..."; \
			git fetch --depth=1 origin "$(LLAMA_CPP_COMMIT)" 2>/dev/null || git fetch origin; \
		fi; \
		git checkout -q "$(LLAMA_CPP_COMMIT)" && echo "      llama.cpp fixado em $(LLAMA_CPP_COMMIT)"; \
	else \
		echo "      AVISO: LLAMA_CPP_COMMIT vazio — usando tip de master (não reproduzível)"; \
	fi
	@# Patch glibc 2.40+ / Debian trixie incompatibility com cudafe++
	@$(MAKE) _patch-glibc-cuda
	@# Aplicar patches de grammar (MAX_REPETITION_THRESHOLD 2000->100000 + auto-anchor).
	@# Trade-off do limite documentado em docs/explanation/architecture.md (schemas
	@# grandes passam a compilar; schema patológico pode gerar gramática enorme).
	@if [ -f "$(PWD)/llama-cpp-grammar-patches.patch" ]; then \
		echo "      Aplicando grammar patches..."; \
		cd "$(LLAMA_CPP_DIR)" && git apply --check "$(PWD)/llama-cpp-grammar-patches.patch" 2>/dev/null && \
			git apply "$(PWD)/llama-cpp-grammar-patches.patch" && \
			echo "      Grammar patches aplicados" || \
			echo "      WARN: grammar patches já aplicados ou conflitam"; \
	fi
	@# Compilar
	@# Compilar (RTX 3090 sm_86 + all-quants FA para KV cache alternativos)
	@cd "$(LLAMA_CPP_DIR)" && cmake -B build \
		-DGGML_CUDA=ON \
		-DCMAKE_CUDA_COMPILER="$(CUDA_HOME)/bin/nvcc" \
		-DCMAKE_BUILD_TYPE=Release \
		-DLLAMA_BUILD_SERVER=ON \
		-DGGML_CUDA_FA_ALL_QUANTS=ON \
		-DCMAKE_CUDA_ARCHITECTURES=86 \
		-DCMAKE_CUDA_FLAGS="--allow-unsupported-compiler" \
		-DCUDA_TOOLKIT_ROOT_DIR="$(CUDA_HOME)" \
		2>&1 | tail -5
	@cd "$(LLAMA_CPP_DIR)" && cmake --build build --config Release \
		-j$$(nproc) --target llama-server 2>&1 | tail -5
	@test -f "$(LLAMA_SERVER)" && echo "      OK — $(LLAMA_SERVER)"

##############################################################################
# [5b] ATUALIZAR llama-server (pull + rebuild)
##############################################################################
update-llama-server:
	@test -d "$(LLAMA_CPP_DIR)/.git" || (echo "ERRO: $(LLAMA_CPP_DIR) não é um repo git" && exit 1)
	@echo "[5b] Atualizando llama.cpp..."
	@cd "$(LLAMA_CPP_DIR)" && git stash 2>/dev/null || true
	@if [ -n "$(LLAMA_CPP_COMMIT)" ]; then \
		echo "      Fixado em LLAMA_CPP_COMMIT=$(LLAMA_CPP_COMMIT) (bump: LLAMA_CPP_COMMIT=<sha> make update-llama-server)"; \
		cd "$(LLAMA_CPP_DIR)" && (git cat-file -e "$(LLAMA_CPP_COMMIT)^{commit}" 2>/dev/null || git fetch --depth=1 origin "$(LLAMA_CPP_COMMIT)" 2>/dev/null || git fetch origin); \
		cd "$(LLAMA_CPP_DIR)" && git checkout -q "$(LLAMA_CPP_COMMIT)"; \
	else \
		echo "      LLAMA_CPP_COMMIT vazio — seguindo tip de master"; \
		cd "$(LLAMA_CPP_DIR)" && git pull --ff-only origin master 2>&1 | tail -3; \
	fi
	@echo "      Aplicando patches (grammar)..."
	@cd "$(LLAMA_CPP_DIR)" && git apply --check "$(PWD)/llama-cpp-grammar-patches.patch" 2>/dev/null && \
		git apply "$(PWD)/llama-cpp-grammar-patches.patch" && \
		echo "      Patches aplicados com sucesso" || \
		echo "      WARN: patches já aplicados ou conflitam (ok se já aplicado)"
	@echo "      Compilando..."
	@cd "$(LLAMA_CPP_DIR)" && cmake -B build \
		-DGGML_CUDA=ON \
		-DCMAKE_CUDA_COMPILER="$(CUDA_HOME)/bin/nvcc" \
		-DCMAKE_BUILD_TYPE=Release \
		-DLLAMA_BUILD_SERVER=ON \
		-DGGML_CUDA_FA_ALL_QUANTS=ON \
		-DCMAKE_CUDA_ARCHITECTURES=86 \
		-DCMAKE_CUDA_FLAGS="--allow-unsupported-compiler" \
		-DCUDA_TOOLKIT_ROOT_DIR="$(CUDA_HOME)" \
		2>&1 | tail -3
	@cd "$(LLAMA_CPP_DIR)" && cmake --build build --config Release \
		-j$$(nproc) --target llama-server 2>&1 | tail -5
	@test -f "$(LLAMA_SERVER)" && echo "      OK — versão: $$($(LLAMA_SERVER) --version 2>&1 | head -1)"

##############################################################################
# [5c] REBUILDAR llama-server (forçado — remove binário primeiro)
##############################################################################
rebuild-llama-server:
	@rm -f "$(LLAMA_SERVER)"
	@rm -f "$(LLAMA_CPP_DIR)/build/CMakeCache.txt"
	@$(MAKE) build-llama-server

# Patch para compatibilidade glibc 2.40 + nvcc (Debian trixie)
_patch-glibc-cuda:
	@CDEFS="/usr/include/x86_64-linux-gnu/sys/cdefs.h"; \
	MATHCALLS="/usr/include/x86_64-linux-gnu/bits/mathcalls-macros.h"; \
	if [ -f "$$CDEFS" ] && ! grep -q "__CUDACC__.*__THROW" "$$CDEFS" 2>/dev/null; then \
		echo "      Aplicando patch glibc/cudafe++ (Debian trixie)..."; \
		cp "$$CDEFS" "$$CDEFS.orig" 2>/dev/null || true; \
		python3 -c " \
import re, sys; \
f='$$CDEFS'; c=open(f).read(); \
old='#   if __cplusplus >= 201103L\n#    define __THROW\tnoexcept (true)\n#   else\n#    define __THROW\tthrow ()\n#   endif'; \
new='#   if defined __CUDACC__\n#    define __THROW\n#    define __THROWNL\n#   elif __cplusplus >= 201103L\n#    define __THROW\tnoexcept (true)\n#   else\n#    define __THROW\tthrow ()\n#   endif'; \
sys.stdout.write(c.replace(old, new) if old in c else c)" > "$$CDEFS.tmp" && mv "$$CDEFS.tmp" "$$CDEFS"; \
		if [ -f "$$MATHCALLS" ] && ! grep -q "__CUDACC__" "$$MATHCALLS" 2>/dev/null; then \
			cp "$$MATHCALLS" "$$MATHCALLS.orig" 2>/dev/null || true; \
			python3 -c " \
import sys; \
f='$$MATHCALLS'; c=open(f).read(); \
old='#define __MATHCALL_VEC(function, suffix, args) \t\\\\\n  __SIMD_DECL (__MATH_PRECNAME (function, suffix)) \\\\\n  __MATHCALL (function, suffix, args)\n\n#define __MATHDECL_VEC(type, function,suffix, args) \\\\\n  __SIMD_DECL (__MATH_PRECNAME (function, suffix)) \\\\\n  __MATHDECL(type, function,suffix, args)'; \
new='#ifdef __CUDACC__\n#define __MATHCALL_VEC(function, suffix, args) __MATHCALL (function, suffix, args)\n#define __MATHDECL_VEC(type, function,suffix, args) __MATHDECL(type, function,suffix, args)\n#else\n'+old+'\n#endif'; \
sys.stdout.write(c.replace(old, new) if old in c else c)" > "$$MATHCALLS.tmp" && mv "$$MATHCALLS.tmp" "$$MATHCALLS"; \
		fi; \
	fi

# Reverte o patch de headers glibc/CUDA restaurando os backups .orig.
# ATENÇÃO: _patch-glibc-cuda modifica /usr/include (headers do sistema). O
# ideal seria um container com CUDA/GCC compatíveis; enquanto isso, este alvo
# permite desfazer a alteração no sistema.
unpatch-glibc-cuda:
	@CDEFS="/usr/include/x86_64-linux-gnu/sys/cdefs.h"; \
	MATHCALLS="/usr/include/x86_64-linux-gnu/bits/mathcalls-macros.h"; \
	restored=0; \
	if [ -f "$$CDEFS.orig" ]; then mv "$$CDEFS.orig" "$$CDEFS" && echo "      Restaurado $$CDEFS" && restored=1; fi; \
	if [ -f "$$MATHCALLS.orig" ]; then mv "$$MATHCALLS.orig" "$$MATHCALLS" && echo "      Restaurado $$MATHCALLS" && restored=1; fi; \
	[ "$$restored" = "1" ] && echo "  ✓ Headers glibc/CUDA revertidos" || echo "  Nenhum backup .orig encontrado (nada a reverter)"

##############################################################################
# [6] COMPILAR llama-cpp-python COM CUDA
##############################################################################
build-llama-cpp-python: $(SENTINEL_VENV) setup-cuda _patch-glibc-cuda
	@echo "[6/8] Verificando llama-cpp-python com suporte GPU..."
	@if $(PYTHON) -c "from llama_cpp import llama_supports_gpu_offload; assert llama_supports_gpu_offload()" 2>/dev/null; then \
		echo "      OK — GPU offload já ativo"; \
	else \
		echo "      Compilando llama-cpp-python com CUDA (pode levar 5-10 min)..."; \
		echo "      $$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"; \
		CUDACXX="$(CUDA_HOME)/bin/nvcc" \
		NVCC_PREPEND_FLAGS="--allow-unsupported-compiler" \
		CMAKE_ARGS="-DGGML_CUDA=on -DCUDA_TOOLKIT_ROOT_DIR=$(CUDA_HOME)" \
		FORCE_CMAKE=1 \
		$(PIP) install "llama-cpp-python[server]" \
			--no-binary llama-cpp-python \
			--no-cache-dir \
			--quiet && \
		$(PYTHON) -c "from llama_cpp import llama_supports_gpu_offload; assert llama_supports_gpu_offload(), 'GPU offload FAILED'" && \
		echo "      OK — GPU offload ativo"; \
	fi

##############################################################################
# [7] BAIXAR MODELO GGUF
##############################################################################
download-model: $(SENTINEL_MODEL)

$(SENTINEL_MODEL): $(SENTINEL_VENV) install-python-deps
	@echo "[7/8] Baixando modelo GGUF..."
	@mkdir -p "$(MODEL_DIR)"
	@if [ -z "$(HF_TOKEN)" ]; then \
		echo "  AVISO: HUGGINGFACE_TOKEN não definido em .env"; \
		echo "  Copie .env.example para .env e preencha o token."; \
	fi
	@MODEL_HF_RESOLVED="$${MODEL_HF:-unsloth/Qwen3.6-35B-A3B-MTP-GGUF}"; \
	echo "      Repositório: $$MODEL_HF_RESOLVED"; \
	echo "      Arquivo: $(MODEL_FILE) (~22.6 GB)"; \
	HF_TOKEN="$(HF_TOKEN)" \
	$(VENV)/bin/hf download "$$MODEL_HF_RESOLVED" "$(MODEL_FILE)" \
		--local-dir "$(MODEL_DIR)"
	@echo "      OK — $(MODEL_DIR)/$(MODEL_FILE)"

##############################################################################
# SERVIDOR
##############################################################################
start: _check-ready
	bash "$(PROJECT_ROOT)/scripts/start-server.sh"

start-bg: _check-ready
	@mkdir -p "$(PROJECT_ROOT)/data/logs"
	@bash "$(PROJECT_ROOT)/scripts/start-server.sh" >> "$(LOG)" 2>&1 &
	@echo "Servidor iniciado em background. Acompanhe: make logs"

stop:
	@pkill llama-server 2>/dev/null && echo "Servidor parado. VRAM liberada — Ollama pode usar a GPU novamente." || echo "Nenhum servidor rodando."

restart: stop
	@$(MAKE) start-bg

status:
	@if curl -sf http://localhost:8000/health > /dev/null 2>&1; then \
		echo "Servidor: RODANDO em http://localhost:8000/v1 (modelo: $${SERVED_NAME:-qwen3})"; \
		nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv,noheader 2>/dev/null | awk '{print "GPU:     "$$0}'; \
	else \
		echo "Servidor: PARADO"; \
	fi

logs:
	@mkdir -p "$(PROJECT_ROOT)/data/logs"
	tail -f "$(LOG)"

test:
	@$(PYTHON) "$(PROJECT_ROOT)/tests/test_api.py"

benchmark: _check-ready
	@$(PYTHON) "$(PROJECT_ROOT)/tests/benchmark.py" $(ARGS)

# Instala o serviço systemd a partir do template, substituindo __PROJECT_ROOT__ pelo
# caminho real deste repo → portável (funciona em qualquer VM/diretório).
install-service:
	@chmod +x "$(PROJECT_ROOT)/scripts/start-server.sh" "$(PROJECT_ROOT)/scripts/setup.sh"
	@mkdir -p "$(PROJECT_ROOT)/data/logs"
	@sed "s|__PROJECT_ROOT__|$(PROJECT_ROOT)|g" \
		"$(PROJECT_ROOT)/infra/llama-server/qwen-server.service" \
		| $(SUDO) tee "$(SERVICE_DEST)" > /dev/null
	@$(SUDO) systemctl daemon-reload
	@echo "✓ Serviço '$(SERVICE_NAME)' instalado em $(SERVICE_DEST) (PROJECT_ROOT=$(PROJECT_ROOT))."
	@echo "  make enable-service    → auto-start no boot + Restart=always (recomendado)"
	@echo "  make start-service     → inicia agora sem habilitar no boot"
	@echo "  make uninstall-service → remove o serviço"

# Remove completamente o serviço (para levar/limpar a VM).
uninstall-service:
	@$(SUDO) systemctl disable --now $(SERVICE_NAME) 2>/dev/null || true
	@$(SUDO) rm -f "$(SERVICE_DEST)"
	@$(SUDO) systemctl daemon-reload
	@echo "✓ Serviço '$(SERVICE_NAME)' removido. O código do repo permanece intacto."

enable-service:
	@$(SUDO) systemctl enable --now $(SERVICE_NAME)
	@echo "✓ Serviço habilitado (auto-start no boot + Restart=always) e iniciado."
	@echo "  Estado: make service-status   Logs: make service-logs"

disable-service:
	@$(SUDO) systemctl disable --now $(SERVICE_NAME) 2>/dev/null || true
	@echo "✓ Serviço desabilitado — não inicia mais no boot (arquivo continua instalado)."

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
# CAPTURA DE CONTEÚDO (debug) — liga o log de prompt+geração e analisa
##############################################################################
# Reinicia via systemd se o serviço estiver ativo, senão via make restart.
_capture-restart:
	@if systemctl is-active --quiet $(SERVICE_NAME) 2>/dev/null; then \
		echo "Reiniciando via systemd ($(SERVICE_NAME))..."; $(SUDO) systemctl restart $(SERVICE_NAME); \
	else \
		echo "Reiniciando via make restart..."; $(MAKE) restart; \
	fi

capture-on:
	@grep -q '^CAPTURE_LOG=' "$(PROJECT_ROOT)/.env" 2>/dev/null \
		&& sed -i 's/^CAPTURE_LOG=.*/CAPTURE_LOG=true/' "$(PROJECT_ROOT)/.env" \
		|| echo 'CAPTURE_LOG=true' >> "$(PROJECT_ROOT)/.env"
	@echo "✓ CAPTURE_LOG=true — reiniciando p/ ligar a captura..."
	@$(MAKE) _capture-restart
	@echo "  Reproduza o problema e rode:  make capture-report"

capture-off:
	@grep -q '^CAPTURE_LOG=' "$(PROJECT_ROOT)/.env" 2>/dev/null \
		&& sed -i 's/^CAPTURE_LOG=.*/CAPTURE_LOG=false/' "$(PROJECT_ROOT)/.env" || true
	@echo "✓ CAPTURE_LOG=false — reiniciando p/ desligar a captura..."
	@$(MAKE) _capture-restart

capture-report:
	@$(PYTHON) "$(PROJECT_ROOT)/scripts/analyze-capture.py" $(ARGS)

clean-capture:
	@rm -rf "$(PROJECT_ROOT)/data/logs/capture"
	@echo "✓ Captura limpa (data/logs/capture removido)."

# Rotação de logs (server.log + captura) — portável, substitui o caminho no install.
install-logrotate:
	@sed "s|__PROJECT_ROOT__|$(PROJECT_ROOT)|g" \
		"$(PROJECT_ROOT)/infra/logrotate/qwen-logs" \
		| $(SUDO) tee "$(LOGROTATE_DEST)" > /dev/null
	@$(SUDO) logrotate --debug "$(LOGROTATE_DEST)" >/dev/null 2>&1 && echo "✓ logrotate instalado e validado em $(LOGROTATE_DEST)." || echo "✓ logrotate instalado em $(LOGROTATE_DEST) (valide com: logrotate --debug $(LOGROTATE_DEST))."

uninstall-logrotate:
	@$(SUDO) rm -f "$(LOGROTATE_DEST)"
	@echo "✓ logrotate removido ($(LOGROTATE_DEST))."

##############################################################################
# GESTÃO DE CONFLITO OLLAMA/GPU
##############################################################################
configure-ollama:
	@echo "Configurando Ollama para liberar VRAM mais rápido..."
	@CONF="/etc/systemd/system/ollama.service.d/10-local.conf"; \
	if [ -f "$$CONF" ]; then \
		sudo sed -i 's/OLLAMA_KEEP_ALIVE=.*/OLLAMA_KEEP_ALIVE=5m/' "$$CONF"; \
		sudo systemctl daemon-reload; \
		sudo systemctl restart ollama; \
		echo "  ✓ OLLAMA_KEEP_ALIVE → 5m (libera VRAM 5 min após último uso)"; \
		echo "  Antes: 30 minutos. Agora: 5 minutos."; \
	else \
		echo "  Arquivo de config não encontrado em $$CONF"; \
		echo "  Adicione manualmente: Environment=\"OLLAMA_KEEP_ALIVE=5m\""; \
	fi

ollama-unload:
	@echo "Forçando Ollama a liberar todos os modelos da GPU..."
	@MODELS=$$(curl -s http://localhost:11434/api/ps 2>/dev/null | \
		python3 -c "import json,sys; d=json.load(sys.stdin); print('\n'.join(m['name'] for m in d.get('models',[])))" 2>/dev/null); \
	if [ -n "$$MODELS" ]; then \
		echo "$$MODELS" | while read M; do \
			curl -s http://localhost:11434/api/generate \
				-d "{\"model\":\"$$M\",\"keep_alive\":0,\"prompt\":\"\"}" > /dev/null 2>&1; \
			echo "  ✓ $$M descarregado"; \
		done; \
	else \
		echo "  Nenhum modelo carregado no Ollama."; \
	fi
	@nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader 2>/dev/null | \
		awk '{print "  GPU: "$$0}'

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
# UPDATE CHAT TEMPLATE
##############################################################################
update-template:
	@echo "Baixando template froggeric mais recente..."
	@mkdir -p "$(PROJECT_ROOT)/data/templates/custom"
	@TMPFILE=$$(mktemp); \
	URL="https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates/resolve/main/chat_template.jinja"; \
	if curl -sL --fail "$$URL" -o "$$TMPFILE" 2>/dev/null; then \
		VERSION=$$(grep -oP 'template_version\s*=\s*"\K[^"]+' "$$TMPFILE" 2>/dev/null || echo "unknown"); \
		echo "  Versao baixada: $$VERSION"; \
		cp "$(PROJECT_ROOT)/data/templates/custom/chat_template_v21.jinja" \
			"$(PROJECT_ROOT)/data/templates/custom/chat_template_v21.jinja.bak" 2>/dev/null || true; \
		cp "$$TMPFILE" "$(PROJECT_ROOT)/data/templates/custom/chat_template_v21.jinja"; \
		if [ -f "$(PROJECT_ROOT)/data/templates/chat_template.jinja" ]; then \
			cp "$$TMPFILE" "$(PROJECT_ROOT)/data/templates/chat_template.jinja"; \
		fi; \
		echo "  ✓ Pristine salvo em custom/chat_template_v21.jinja"; \
		if [ -f "$(PROJECT_ROOT)/data/templates/custom/chat_template_local.jinja" ]; then \
			echo ""; \
			echo "  ATENCAO: chat_template_local.jinja (ativo) NAO foi alterado."; \
			echo "  Para ver diferencas com a nova versao:"; \
			echo "    diff data/templates/custom/chat_template_v21.jinja \\"; \
			echo "         data/templates/custom/chat_template_local.jinja"; \
			echo "  E mescle as mudancas manualmente em chat_template_local.jinja."; \
		fi; \
	else \
		echo "  ERRO: nao foi possivel baixar template de $$URL"; \
		echo "  Verifique a URL em: https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates"; \
		rm -f "$$TMPFILE"; \
		exit 1; \
	fi; \
	rm -f "$$TMPFILE"

##############################################################################
# BENCHMARK
##############################################################################
benchmark-sweep: _check-ready
	@$(PYTHON) "$(PROJECT_ROOT)/tests/benchmark.py" $(ARGS)

##############################################################################
# LIMPEZA
##############################################################################
clean:
	@echo "Removendo modelo, logs e venv..."
	@rm -rf "$(MODEL_DIR)/"*.gguf "$(PROJECT_ROOT)/data/logs/"* "$(VENV)"
	@echo "Código e templates mantidos. Execute 'make setup' para reconfigurar."

clean-logs:
	@DAYS="$${LOG_RETENTION_DAYS:-7}"; \
	echo "Removendo logs com mais de $$DAYS dias em data/logs/..."; \
	cd "$(PROJECT_ROOT)/data/logs" && \
	find . -maxdepth 1 -type f ! -name '.gitkeep' -mtime +$$DAYS -delete -print | \
	while read f; do echo "  removido: $$f"; done; \
	echo "Pronto."

cron-clean-logs:
	@DAYS="$${LOG_RETENTION_DAYS:-7}"; \
	CMD="cd $(PROJECT_ROOT) && make clean-logs"; \
	CRON_ID="qwen-clean-logs"; \
	(crontab -l 2>/dev/null | grep -v "$$CRON_ID") | \
	(echo "0 3 * * * $$CMD  # $$CRON_ID") | crontab -; \
	echo "Cron instalado: todo dia às 03:00 (retention=$$DAYS dias)"
	@echo "Para mudar: edite LOG_RETENTION_DAYS no .env e rode make cron-clean-logs novamente"

cron-remove-clean-logs:
	@crontab -l 2>/dev/null | grep -v "qwen-clean-logs" | crontab - 2>/dev/null || true
	@echo "Cron de limpeza de logs removido."

##############################################################################
# INTERNO
##############################################################################
_check-ready:
	@if [ ! -f "$(LLAMA_SERVER)" ]; then \
		echo "ERRO: llama-server não encontrado. Execute: make setup"; exit 1; \
	fi
	@if [ ! -f "$(SENTINEL_MODEL)" ]; then \
		echo "ERRO: modelo não encontrado. Execute: make download-model"; exit 1; \
	fi
