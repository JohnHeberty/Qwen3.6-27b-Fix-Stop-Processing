"""
LoopGuard — guardrail customizado do LiteLLM pra detectar tool_calls
repetidas (mesmo nome + mesmos argumentos) dentro do histórico de
mensagens do próprio request, e cortar o loop ANTES de devolver a
resposta pro OpenClaw.

Não precisa de estado externo (Redis, banco): cada request já traz o
histórico completo da conversa em `inputs["structured_messages"]`, então
a contagem de repetição é reconstruída a cada chamada a partir disso.
Isso é intencional — funciona como uma segunda camada, independente do
`tools.loopDetection` do OpenClaw (que já foi ajustado separadamente).

Comportamento em degraus:
  - 1..SOFT_THRESHOLD-1 repetições idênticas: deixa passar.
  - >= SOFT_THRESHOLD: modifica a resposta — remove a tool_call repetida
    e injeta um aviso de texto, dando ao modelo uma chance de mudar de
    estratégia (não derruba a conexão, não gera erro pro OpenClaw).
  - >= HARD_THRESHOLD: bloqueia de vez (levanta exceção), pra garantir
    que o loop pare mesmo se o modelo ignorar o aviso.

Registro no config.yaml:

    guardrails:
      - guardrail_name: "loop-guard"
        litellm_params:
          guardrail: loop_guard.LoopGuard
          mode: "post_call"
"""

import hashlib
import json
from typing import Any, Literal, Optional

from litellm.integrations.custom_guardrail import CustomGuardrail

# Repetições idênticas antes de avisar/bloquear.
# Propositalmente mais baixo que o warningThreshold=5 do OpenClaw:
# essa camada roda no proxy, então pega o padrão um pouco mais cedo.
SOFT_THRESHOLD = 3
HARD_THRESHOLD = 6

# Quantas mensagens recentes olhar pra trás no histórico.
# Não precisa cobrir a conversa inteira — o loop de tool-call
# se manifesta em turnos consecutivos, não espalhado no tempo.
HISTORY_WINDOW = 40


def _signature(name: str, arguments: Any) -> str:
    """Assinatura estável de uma tool_call: nome + args canonicalizados."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            pass
    try:
        canonical = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
    except TypeError:
        canonical = str(arguments)
    raw = f"{name}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _extract_tool_call_signatures(tool_calls: list) -> list[str]:
    sigs = []
    for tc in tool_calls or []:
        fn = tc.get("function") if isinstance(tc, dict) else None
        if not fn:
            continue
        name = fn.get("name", "")
        args = fn.get("arguments", "")
        sigs.append(_signature(name, args))
    return sigs


def _count_prior_occurrences(messages: list, target_sig: str, window: int) -> int:
    """Conta quantas vezes essa assinatura já apareceu em tool_calls
    de mensagens assistant anteriores, dentro da janela recente."""
    count = 0
    recent = messages[-window:] if messages else []
    for msg in recent:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls") or []
        for sig in _extract_tool_call_signatures(tool_calls):
            if sig == target_sig:
                count += 1
    return count


class LoopGuard(CustomGuardrail):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def apply_guardrail(
        self,
        inputs: dict,
        request_data: dict,
        input_type: Literal["request", "response"],
        logging_obj: Optional[Any] = None,
    ) -> dict:
        # Só nos interessa checar o que o modelo ACABOU de gerar.
        if input_type != "response":
            return inputs

        tool_calls = inputs.get("tool_calls") or []
        if not tool_calls:
            return inputs

        messages = inputs.get("structured_messages") or request_data.get("messages") or []

        max_repeat_count = 0
        offending_names = []

        for tc in tool_calls:
            fn = tc.get("function") if isinstance(tc, dict) else None
            if not fn:
                continue
            name = fn.get("name", "?")
            args = fn.get("arguments", "")
            sig = _signature(name, args)
            prior = _count_prior_occurrences(messages, sig, HISTORY_WINDOW)
            if prior > max_repeat_count:
                max_repeat_count = prior
                offending_names = [name]
            elif prior == max_repeat_count and prior > 0:
                offending_names.append(name)

        if max_repeat_count < SOFT_THRESHOLD:
            return inputs

        if max_repeat_count >= HARD_THRESHOLD:
            raise Exception(
                f"[loop-guard] Bloqueado: tool_call '{offending_names}' repetida "
                f"{max_repeat_count}x com argumentos idênticos nas últimas "
                f"{HISTORY_WINDOW} mensagens. Encerrando o turno para evitar loop."
            )

        # Faixa intermediária: remove a(s) tool_call(s) repetida(s) e
        # injeta um aviso textual, deixando o modelo responder de novo
        # em vez de travar a conexão.
        warning = (
            f"[loop-guard] Você chamou '{offending_names}' com os mesmos "
            f"argumentos {max_repeat_count} vezes seguidas. Isso não está "
            f"progredindo — pare de repetir e tente uma abordagem diferente, "
            f"ou explique por que está travado."
        )
        inputs["tool_calls"] = []
        existing_texts = inputs.get("texts") or []
        inputs["texts"] = existing_texts + [warning]

        return inputs
