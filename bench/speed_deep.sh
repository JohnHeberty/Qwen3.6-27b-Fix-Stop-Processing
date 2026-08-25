#!/bin/bash
# Deeper speed test — longer generations + verify DFlash2 speculative decoding

echo "=== Deep Speed Test ==="
echo ""

# Test 1: Long generation (1000 tokens)
echo "--- Long generation (1000 tokens) ---"
RESPONSE=$(curl -s http://localhost:18020/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen3.8-27b",
        "messages": [{"role": "user", "content": "Write a comprehensive essay about the history and evolution of artificial intelligence, from the earliest days to modern large language models."}],
        "max_tokens": 1000,
        "temperature": 0.7
    }')
echo "$RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
u = d.get('usage', {})
m = d['choices'][0]['message']
print(f'  Prompt tokens: {u.get(\"prompt_tokens\",0)}')
print(f'  Completion tokens: {u.get(\"completion_tokens\",0)}')
print(f'  Content: {len(m.get(\"content\") or \"\")} chars')
print(f'  Finish: {d[\"choices\"][0].get(\"finish_reason\")}')
"
echo ""

# Test 2: Verify DFlash2 is active via server log
echo "--- DFlash2 Status (last 30 log lines) ---"
grep -E "(spec|draft|dflash|DFlash|speculative)" /root/qwen3/data/logs/qwen38-27b.log | tail -10
echo ""

# Test 3: Verify tool calling with proper format
echo "--- Tool Call (hermes format) ---"
curl -s http://localhost:18020/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen3.8-27b",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Use tools when appropriate."},
            {"role": "user", "content": "What time is it in Tokyo right now?"}
        ],
        "max_tokens": 200,
        "tools": [{"type": "function", "function": {"name": "get_current_time", "description": "Get current time for a timezone", "parameters": {"type": "object", "properties": {"timezone": {"type": "string", "description": "IANA timezone like Asia/Tokyo"}}, "required": ["timezone"]}}}]
    }' | python3 -c "
import sys, json
d = json.load(sys.stdin)
msg = d['choices'][0]['message']
tc = msg.get('tool_calls', [])
reasoning = msg.get('reasoning', '')
print(f'  Tool calls: {len(tc)}')
if tc:
    print(f'  Name: {tc[0][\"function\"][\"name\"]}')
    print(f'  Args: {tc[0][\"function\"][\"arguments\"]}')
else:
    content = msg.get('content','')
    print(f'  Content (first 200): {content[:200]}')
print(f'  Finish: {d[\"choices\"][0].get(\"finish_reason\")}')
print(f'  Reasoning: {reasoning[:150] if reasoning else \"(none)\"}')
" 2>/dev/null
echo ""

echo "=== Done ==="
