#!/usr/bin/env python3
"""
Test suite for Qwen v21 chat templates.
Tests logical correctness using Python Jinja2 (minijinja compatibility verified separately).

Usage:
    python3 data/templates/scripts/test_template.py
    python3 data/templates/scripts/test_template.py qwen3.6   # test one variant
"""

import sys
import os
from pathlib import Path
from jinja2 import Environment

# ── Setup ──────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
PROJECT_ROOT = ROOT.parent.parent
VARIANTS = ["root"]

def load_template() -> str:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("TEMPLATE_FILE=") and not line.startswith("#"):
                template_rel = line.split("=", 1)[1].strip()
                template_path = PROJECT_ROOT / template_rel
                if template_path.exists():
                    return template_path.read_text(encoding="utf-8")
                print(f"  Template not found: {template_path}")
                sys.exit(1)
    print("  TEMPLATE_FILE not set in .env")
    sys.exit(1)

def render(template_src: str, messages: list, tools=None,
           add_generation_prompt: bool = True,
           enable_thinking=None, preserve_thinking=None, error_warnings=None) -> str:
    env = Environment(keep_trailing_newline=False)
    env.globals["raise_exception"] = lambda msg: (_ for _ in ()).throw(ValueError(msg))
    tmpl = env.from_string(template_src)
    kwargs = dict(messages=messages, tools=tools, add_generation_prompt=add_generation_prompt)
    if enable_thinking is not None:
        kwargs["enable_thinking"] = enable_thinking
    if preserve_thinking is not None:
        kwargs["preserve_thinking"] = preserve_thinking
    if error_warnings is not None:
        kwargs["error_warnings"] = error_warnings
    return tmpl.render(**kwargs)

# ── Test helpers ───────────────────────────────────────────────────────────────

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

results = []

def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append(condition)
    suffix = f"  ({detail})" if detail and not condition else ""
    print(f"  {status}  {name}{suffix}")

# ── Tests ──────────────────────────────────────────────────────────────────────

def test_xml_tool_call_format(t: str):
    """Tool calls in history must use XML <function=...> format, not JSON."""
    messages = [
        {"role": "user", "content": "Get weather for Paris"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "get_weather",
                                      "arguments": {"city": "Paris", "units": "celsius"}}}]},
        {"role": "tool", "content": "Sunny, 22°C"},
    ]
    tools = [{"name": "get_weather", "description": "Get weather",
              "parameters": {"type": "object",
                             "properties": {"city": {"type": "string"},
                                            "units": {"type": "string"}},
                             "required": ["city"]}}]
    out = render(t, messages, tools=tools)
    check("XML format: <function=...> present", "<function=get_weather>" in out,
          f"got: {repr(out[out.find('<tool_call>'):out.find('<tool_call>')+120] if '<tool_call>' in out else 'no <tool_call>')}")
    check("XML format: <parameter=city> present", "<parameter=city>" in out)
    check("XML format: <parameter=units> present", "<parameter=units>" in out)
    check("XML format: </function> present", "</function>" in out)
    check("XML format: JSON {\"name\": absent in tool_call section",
          '{"name":' not in out[out.rfind('<tool_call>'):] if '<tool_call>' in out else True,
          f"tool_call section: {repr(out[out.rfind('<tool_call>'):out.rfind('<tool_call>')+120] if '<tool_call>' in out else 'none')}")
    check("XML format: tool_instructions mention <function=", "<function=" in out)

def test_tool_instructions_format(t: str):
    """System prompt tool instructions must show XML example, not JSON."""
    messages = [{"role": "user", "content": "Hello"}]
    tools = [{"name": "noop", "description": "no-op",
              "parameters": {"type": "object", "properties": {}, "required": []}}]
    out = render(t, messages, tools=tools)
    check("Instructions: XML example present", "<function=example_function_name>" in out)
    check("Instructions: JSON example absent", '{"name": "tool_name"' not in out)
    check("Instructions: <parameter= in example", "<parameter=example_parameter_1>" in out)

def test_normal_generation_prompt(t: str):
    """Normal generation prompt opens <think> block."""
    messages = [{"role": "user", "content": "Hello"}]
    out = render(t, messages)
    check("Normal gen-prompt: ends with <think>\\n", out.endswith("<think>\n"),
          f"tail: {repr(out[-30:])}")

def test_thinking_bypass(t: str):
    """When thinking disabled via enable_thinking=False, bypass is injected."""
    messages = [{"role": "user", "content": "Hello"}]
    out = render(t, messages, enable_thinking=False)
    check("Think bypass: <think>\\n\\n</think>\\n\\n present",
          "<think>\n\n</think>\n\n" in out, f"tail: {repr(out[-60:])}")
    check("Think bypass: no open-only <think>\\n at end",
          not out.endswith("<think>\n"))

def test_think_off_token(t: str):
    """<|think_off|> in system message disables thinking."""
    messages = [
        {"role": "system", "content": "You are helpful.<|think_off|>"},
        {"role": "user", "content": "Hello"},
    ]
    out = render(t, messages)
    check("<|think_off|> disables thinking", "<think>\n\n</think>\n\n" in out)
    check("<|think_off|> token stripped from output", "<|think_off|>" not in out)

def test_think_on_after_off(t: str):
    """<|think_on|> re-enables thinking after <|think_off|>."""
    messages = [
        {"role": "system", "content": "<|think_off|>"},
        {"role": "user", "content": "Step 1"},
        {"role": "assistant", "content": "Done."},
        {"role": "user", "content": "<|think_on|>Now think"},
    ]
    out = render(t, messages)
    check("<|think_on|> re-enables thinking", out.endswith("<think>\n"),
          f"tail: {repr(out[-40:])}")

def test_tier1_error_escalation(t: str):
    """First tool error injects Tier 1 correction hint (requires error_warnings=True)."""
    messages = [
        {"role": "user", "content": "Read a file"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file",
                                      "arguments": {"path": "/foo", "pages": "1-30"}}}]},
        # Precisa casar a heuristica (começa com "Error:").
        {"role": "tool", "content": "Error: page range exceeds maximum of 20 pages per request."},
    ]
    tools = [{"name": "read_file", "description": "Read",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                             "required": ["path"]}}]
    out = render(t, messages, tools=tools, error_warnings=True)
    check("Tier 1: correction hint in gen-prompt",
          "The previous tool call returned an error" in out,
          f"tail: {repr(out[-120:])}")
    check("Tier 1: think block still open (not bypassed)", out.endswith("\n"))

def test_tier2_error_escalation(t: str):
    """Two consecutive tool errors trigger Tier 2 bypass (requires error_warnings=True)."""
    tool_error = "Error: page range exceeds maximum of 20 pages per request."
    messages = [
        {"role": "user", "content": "Read a file"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file",
                                      "arguments": {"path": "/foo", "pages": "1-30"}}}]},
        {"role": "tool", "content": tool_error},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file",
                                      "arguments": {"path": "/foo", "pages": "1-25"}}}]},
        {"role": "tool", "content": tool_error},
    ]
    tools = [{"name": "read_file", "description": "Read",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                             "required": ["path"]}}]
    out = render(t, messages, tools=tools, error_warnings=True)
    check("Tier 2: think bypass injected", "<think>\n\n</think>\n\n" in out,
          f"tail: {repr(out[-200:])}")
    check("Tier 2: escalation warning present",
          "consecutive tool errors" in out or "consecutive" in out,
          f"tail: {repr(out[-200:])}")

def test_length_gated_detection(t: str):
    """Long tool response (code content with 'error') must NOT trigger error flag."""
    long_content = ("// Error handling\nfunction handleError(e) {\n"
                    "  throw new Error('invalid input');\n}\n") * 30  # >> 500 chars
    messages = [
        {"role": "user", "content": "Read the code"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file",
                                      "arguments": {"path": "app.js"}}}]},
        {"role": "tool", "content": long_content},
    ]
    tools = [{"name": "read_file", "description": "Read",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                             "required": ["path"]}}]
    out = render(t, messages, tools=tools)
    check("Length gate: long response with 'error' does NOT trigger hint",
          "The previous tool call returned an error" not in out,
          f"tail: {repr(out[-80:])}")
    check("Length gate: normal gen-prompt after long response",
          out.endswith("<think>\n"), f"tail: {repr(out[-40:])}")

def test_error_counter_resets_on_success(t: str):
    """After a successful tool call, the consecutive failure counter resets."""
    tool_error = "Error: file not found."
    messages = [
        {"role": "user", "content": "Do something"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "/bad"}}}]},
        {"role": "tool", "content": tool_error},  # error → cf=1
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "/good"}}}]},
        {"role": "tool", "content": "file content here " * 30},  # success, long → cf=0
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "/bad2"}}}]},
        {"role": "tool", "content": tool_error},  # error → cf=1 again (not 2)
    ]
    tools = [{"name": "read_file", "description": "Read",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                             "required": ["path"]}}]
    out = render(t, messages, tools=tools, error_warnings=True)
    # Should be Tier 1 (cf=1), not Tier 2 (cf>=2)
    check("Counter reset: Tier 1 after success+new error (not Tier 2)",
          "The previous tool call returned an error" in out and
          "consecutive tool errors" not in out,
          f"tail: {repr(out[-200:])}")

def test_historical_thinking_stripped(t: str):
    """Historical assistant <think> blocks are stripped when preserve_thinking=False."""
    messages = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "<think>\nmy thoughts\n</think>\n\nAnswer 1"},
        {"role": "user", "content": "Q2"},
    ]
    # preserve_thinking default is True (keeps thoughts); stripping only happens when off.
    out = render(t, messages, preserve_thinking=False)
    check("Historical think stripped when preserve_thinking=False", "my thoughts" not in out)

def test_preserve_thinking(t: str):
    """With preserve_thinking=True, historical <think> blocks are kept."""
    messages = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "<think>\nmy thoughts\n</think>\n\nAnswer 1"},
        {"role": "user", "content": "Q2"},
    ]
    out = render(t, messages, preserve_thinking=True)
    check("preserve_thinking=True keeps historical thoughts", "my thoughts" in out)

def test_developer_role(t: str):
    """developer role is accepted (same as system)."""
    messages = [
        {"role": "developer", "content": "You are a coder."},
        {"role": "user", "content": "Write code"},
    ]
    try:
        out = render(t, messages)
        check("developer role: no crash", True)
        check("developer role: content rendered", "You are a coder." in out)
    except Exception as e:
        check("developer role: no crash", False, str(e))

def test_mid_conversation_system(t: str):
    """System messages mid-conversation are rendered chronologically."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "system", "content": "You must now speak in French."},
        {"role": "user", "content": "What's up?"},
    ]
    try:
        out = render(t, messages)
        check("Mid-conv system: no crash", True)
        check("Mid-conv system: content present", "You must now speak in French." in out)
    except Exception as e:
        check("Mid-conv system: no crash", False, str(e))

def test_tool_response_wrapping(t: str):
    """Tool responses are wrapped in <tool_response> tags."""
    messages = [
        {"role": "user", "content": "Get data"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "fetch", "arguments": {"url": "https://example.com"}}}]},
        {"role": "tool", "content": "data here"},
    ]
    tools = [{"name": "fetch", "description": "Fetch URL",
              "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                             "required": ["url"]}}]
    out = render(t, messages, tools=tools)
    check("Tool response: <tool_response> wrapper present", "<tool_response>" in out)
    check("Tool response: content inside wrapper", "data here" in out)

def test_no_tools_no_crash(t: str):
    """Template works without any tools passed."""
    messages = [{"role": "user", "content": "What is 2+2?"}]
    try:
        out = render(t, messages)
        check("No tools: no crash", True)
        check("No tools: normal gen-prompt", out.endswith("<think>\n"))
    except Exception as e:
        check("No tools: no crash", False, str(e))

def test_string_arguments_passthrough(t: str):
    """String tool arguments (pre-serialized JSON) are passed through as-is."""
    messages = [
        {"role": "user", "content": "Search"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "search",
                                      "arguments": '{"query": "python", "limit": 5}'}}]},
        {"role": "tool", "content": "results"},
    ]
    tools = [{"name": "search", "description": "Search",
              "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                             "required": ["query"]}}]
    out = render(t, messages, tools=tools)
    check("String args: passthrough without crash", "search" in out)

# ── New tests for v16 fixes ────────────────────────────────────────────────────

def test_shell_result_false_positive(t: str):
    """Short grep results containing 'error' in identifiers must NOT trigger error flag."""
    shell_result = '$ grep -n "error_message" orchestrator.go (timeout 5s)\n\n661: "error_message": "",\n\nTook 0.1s'
    messages = [
        {"role": "user", "content": "Search for error_message"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "shell",
                                      "arguments": {"cmd": "grep -n error_message file.go"}}}]},
        {"role": "tool", "content": shell_result},
    ]
    tools = [{"name": "shell", "description": "Run shell command",
              "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}},
                             "required": ["cmd"]}}]
    out = render(t, messages, tools=tools)
    check("Shell false-positive: grep with 'error_message' not flagged",
          "The previous tool call returned an error" not in out,
          f"tail: {repr(out[-80:])}")
    check("Shell false-positive: normal gen-prompt after grep result",
          out.endswith("<think>\n"), f"tail: {repr(out[-40:])}")


def test_no_thinking_with_error_escalation(t: str):
    """When enable_thinking=False and a tool errors, correction hint must NOT open a <think> block."""
    tool_error = "Error: page range exceeds maximum of 20 pages per request."
    messages = [
        {"role": "user", "content": "Read a file"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file",
                                      "arguments": {"path": "/foo", "pages": "1-30"}}}]},
        {"role": "tool", "content": tool_error},
    ]
    tools = [{"name": "read_file", "description": "Read",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                             "required": ["path"]}}]
    out = render(t, messages, tools=tools, enable_thinking=False, error_warnings=True)
    check("No-think + error: correction hint present",
          "The previous tool call returned an error" in out,
          f"tail: {repr(out[-120:])}")
    check("No-think + error: does not end with open think block",
          not out.rstrip().endswith("<think>"),
          f"tail: {repr(out[-80:])}")
    check("No-think + error: no unclosed <think> in error section",
          "<think>\nThe previous" not in out,
          f"tail: {repr(out[-120:])}")


def test_error_warnings_disabled_by_default(t: str):
    """Com error_warnings default (off), uma tool error que casaria a heuristica
    NAO deve injetar SYSTEM WARNING nem desligar o thinking."""
    tool_error = "Error: file not found."  # casa a heuristica ("error:")
    messages = [
        {"role": "user", "content": "Read a file"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "/bad"}}}]},
        {"role": "tool", "content": tool_error},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "/bad2"}}}]},
        {"role": "tool", "content": tool_error},  # 2a falha consecutiva
    ]
    tools = [{"name": "read_file", "description": "Read",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                             "required": ["path"]}}]
    # Sem passar error_warnings -> usa o default do template (false).
    out = render(t, messages, tools=tools)
    check("Default off: no SYSTEM WARNING injected", "SYSTEM WARNING" not in out,
          f"tail: {repr(out[-160:])}")
    check("Default off: no Tier-1 correction hint",
          "The previous tool call returned an error" not in out)
    check("Default off: no Tier-2 escalation", "consecutive tool errors" not in out)
    check("Default off: thinking NOT force-disabled (think stays open)",
          out.endswith("<think>\n"), f"tail: {repr(out[-40:])}")


def test_precise_error_detection(t: str):
    """Even with error_warnings=True, detection is PRECISE: only an explicit error
    marker at the START, or a JSON that DECLARES an error, counts as a failure.
    False positives (grep hit, '0 errors', mid-line 'error', logs) must NOT flag."""
    tools = [{"name": "f", "parameters": {"type": "object",
              "properties": {"a": {"type": "string"}}}}]

    def warned(tool_content):
        msgs = [{"role": "user", "content": "x"},
                {"role": "assistant", "content": "",
                 "tool_calls": [{"function": {"name": "f", "arguments": {"a": "b"}}}]},
                {"role": "tool", "content": tool_content}]
        out = render(t, msgs, tools=tools, error_warnings=True)
        return "SYSTEM WARNING" in out

    # Real errors -> must flag
    check("Precise: 'Error:' prefix flags", warned("Error: file not found."))
    check("Precise: Traceback flags", warned("Traceback (most recent call last):\n  File x"))
    check("Precise: JSON {\"error\":...} flags", warned('{"error": "boom"}'))
    check("Precise: JSON {\"ok\": false} flags", warned('{"ok": false, "msg": "x"}'))
    # False positives -> must NOT flag
    check("Precise: grep hit on 'error' NOT flagged",
          not warned('$ grep error_message f.go\n661: "error_message": "",'))
    check("Precise: '0 errors' NOT flagged",
          not warned("Build succeeded with 0 errors, 0 warnings."))
    check("Precise: mid-line 'Error' in code NOT flagged",
          not warned("// Error handling\nfunction handleError(e){throw new Error('x')}"))
    check("Precise: log mentioning 'error' NOT flagged",
          not warned("request ok; no error detected downstream"))


# ── Runner ─────────────────────────────────────────────────────────────────────

TESTS = [
    test_xml_tool_call_format,
    test_tool_instructions_format,
    test_normal_generation_prompt,
    test_thinking_bypass,
    test_think_off_token,
    test_think_on_after_off,
    test_tier1_error_escalation,
    test_tier2_error_escalation,
    test_length_gated_detection,
    test_error_counter_resets_on_success,
    test_historical_thinking_stripped,
    test_preserve_thinking,
    test_developer_role,
    test_mid_conversation_system,
    test_tool_response_wrapping,
    test_no_tools_no_crash,
    test_string_arguments_passthrough,
    test_shell_result_false_positive,
    test_no_thinking_with_error_escalation,
    test_error_warnings_disabled_by_default,
    test_precise_error_detection,
]
results: list[bool] = []

def run_tests():
    print(f"\n{'═'*60}")
    print(f"  Testing v21 Chat Template")
    print(f"{'═'*60}")
    tmpl = load_template()
    for fn in TESTS:
        label = fn.__name__.replace("test_", "").replace("_", " ").title()
        print(f"\n  [{label}]")
        fn(tmpl)

if __name__ == "__main__":
    results.clear()
    run_tests()

    total = len(results)
    passed = sum(results)
    failed = total - passed
    print(f"\n{'═'*60}")
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  \033[91m({failed} failed)\033[0m")
    else:
        print(f"  \033[92m(all passed)\033[0m")
    print(f"{'═'*60}\n")
    sys.exit(0 if failed == 0 else 1)
