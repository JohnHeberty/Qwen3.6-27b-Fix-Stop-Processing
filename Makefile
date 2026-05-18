##############################################################################
# Qwen3.6 27B — Pipeline plug-and-play zero-dependência
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
CUDA_HOME        ?= /usr/local/cuda
MODEL_DIR        ?= $(PROJECT_ROOT)/data/models
MODEL_FILE       ?= Qwen3.6-27B-Q4_K_M.gguf
HF_TOKEN         ?= $(HUGGINGFACE_TOKEN)

.DEFAULT_GOAL := help

# ── Sentinels (arquivos que indicam etapa concluída) ──────────────────────────
SENTINEL_VENV        := $(VENV)/bin/python
SENTINEL_LLAMA       := $(LLAMA_SERVER)
SENTINEL_LLAMACPP_PY := $(VENV)/bin/llama-server
SENTINEL_MODEL       := $(MODEL_DIR)/$(MODEL_FILE)

.PHONY: help setup \
        install-system-deps setup-cuda create-venv install-python-deps \
        build-llama-server build-llama-cpp-python \
        download-model fix-template \
        start start-bg stop restart status logs test \
        install-service enable-service disable-service start-service \
        configure-ollama ollama-unload \
        litellm-start \
        clean

##############################################################################
# HELP
##############################################################################
help:
	@echo ""
	@echo "  Qwen3.6 27B — llama-server GGUF"
	@echo ""
	@echo "  SETUP (zero-dependência):"
	@echo "  make setup              Pipeline completa: instala tudo do zero"
	@echo "  make install-system-deps  [1] Instala Python, cmake, git, build-essential"
	@echo "  make setup-cuda           [2] Verifica / instala CUDA toolkit"
	@echo "  make create-venv          [3] Cria virtualenv Python"
	@echo "  make install-python-deps  [4] Instala gguf, huggingface-hub, etc."
	@echo "  make build-llama-server   [5] Compila llama-server com CUDA"
	@echo "  make build-llama-cpp-python [6] Compila llama-cpp-python com CUDA"
	@echo "  make download-model       [7] Baixa modelo GGUF do HuggingFace"
	@echo "  make fix-template         [8] Aplica template v18 no GGUF"
	@echo ""
	@echo "  SERVIDOR:"
	@echo "  make start              Sobe servidor em foreground (Ctrl+C para parar)"
	@echo "  make start-bg           Sobe em background"
	@echo "  make stop               Para o servidor"
	@echo "  make restart            Para e sobe em background"
	@echo "  make status             Mostra estado e VRAM"
	@echo "  make logs               Acompanha log em tempo real"
	@echo "  make test               Roda suite de testes da API"
	@echo "  make install-service    Registra o serviço systemd (sem auto-start)"
	@echo "  make enable-service     Ativa auto-start no boot (CONFLITA com Ollama)"
	@echo "  make disable-service    Desativa auto-start no boot"
	@echo "  make start-service      Inicia via systemd sem habilitar no boot"
	@echo ""
	@echo "  LIMPEZA:"
	@echo "  make clean              Remove modelo, logs e venv (mantém código)"
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
	@echo "  API: http://localhost:8000/v1  |  Modelo: qwen3"
	@echo ""

##############################################################################
# [0] SETUP COMPLETO — encadeia todas as etapas
##############################################################################
setup: install-system-deps setup-cuda create-venv install-python-deps \
       build-llama-server build-llama-cpp-python download-model fix-template
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
	@# Patch glibc 2.40+ / Debian trixie incompatibility com cudafe++
	@$(MAKE) _patch-glibc-cuda
	@# Compilar
	@cd "$(LLAMA_CPP_DIR)" && cmake -B build \
		-DGGML_CUDA=ON \
		-DCMAKE_CUDA_COMPILER="$(CUDA_HOME)/bin/nvcc" \
		-DCMAKE_BUILD_TYPE=Release \
		-DLLAMA_BUILD_SERVER=ON \
		-DCMAKE_CUDA_FLAGS="--allow-unsupported-compiler" \
		-DCUDA_TOOLKIT_ROOT_DIR="$(CUDA_HOME)" \
		2>&1 | tail -5
	@cd "$(LLAMA_CPP_DIR)" && cmake --build build --config Release \
		-j$$(nproc) --target llama-server 2>&1 | tail -5
	@test -f "$(LLAMA_SERVER)" && echo "      OK — $(LLAMA_SERVER)"

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
	@MODEL_HF_RESOLVED="$${MODEL_HF:-unsloth/Qwen3.6-27B-MTP-GGUF}"; \
	echo "      Repositório: $$MODEL_HF_RESOLVED"; \
	echo "      Arquivo: $(MODEL_FILE) (~16 GB)"; \
	HF_TOKEN="$(HF_TOKEN)" \
	$(VENV)/bin/hf download "$$MODEL_HF_RESOLVED" "$(MODEL_FILE)" \
		--local-dir "$(MODEL_DIR)"
	@echo "      OK — $(MODEL_DIR)/$(MODEL_FILE)"

##############################################################################
# [8] APLICAR TEMPLATE v18
##############################################################################
fix-template: $(SENTINEL_VENV)
	@echo "[8/8] Aplicando template v18..."
	@$(PYTHON) "$(PROJECT_ROOT)/src/fix_template.py"

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
	@pkill -f "llama-server" 2>/dev/null && echo "Servidor parado. VRAM liberada — Ollama pode usar a GPU novamente." || echo "Nenhum servidor rodando."

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

install-service:
	@sudo cp "$(PROJECT_ROOT)/infra/llama-server/qwen-server.service" /etc/systemd/system/
	@sudo systemctl daemon-reload
	@echo "Serviço registrado (NÃO habilitado no boot)."
	@echo "  make enable-service   → ativa auto-start no boot"
	@echo "  make start-service    → inicia agora sem auto-start"
	@echo "  sudo systemctl status qwen-server"

enable-service:
	@sudo systemctl enable qwen-server
	@sudo systemctl start qwen-server
	@echo "Serviço habilitado — inicia automaticamente no boot."
	@echo "ATENÇÃO: conflita com Ollama na GPU (24 GB compartilhados)."
	@echo "Para desabilitar: make disable-service"

disable-service:
	@sudo systemctl disable qwen-server
	@sudo systemctl stop qwen-server 2>/dev/null || true
	@echo "Serviço desabilitado — não inicia mais no boot."

start-service:
	@sudo systemctl start qwen-server
	@echo "Serviço iniciado (sem auto-start no boot)."

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
# LIMPEZA
##############################################################################
clean:
	@echo "Removendo modelo, logs e venv..."
	@rm -rf "$(MODEL_DIR)/"*.gguf "$(PROJECT_ROOT)/data/logs/"* "$(VENV)"
	@echo "Código e templates mantidos. Execute 'make setup' para reconfigurar."

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
