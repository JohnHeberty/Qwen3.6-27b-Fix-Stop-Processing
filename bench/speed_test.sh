#!/bin/bash
# vLLM speed benchmark — measures tok/s for different max_tokens values

echo "=== vLLM Speed Test ==="
echo "Model: qwen3.8-27b | Port: 18020"
echo ""

run_test() {
    local max_tokens=$1
    local label=$2
    local prompt=$3
    
    echo "--- $label (max_tokens=$max_tokens) ---"
    
    START=$(date +%s%N)
    RESPONSE=$(curl -s http://localhost:18020/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"qwen3.8-27b\",
            \"messages\": [{\"role\": \"user\", \"content\": \"$prompt\"}],
            \"max_tokens\": $max_tokens,
            \"temperature\": 0.7
        }" 2>&1)
    END=$(date +%s%N)
    
    WALL_MS=$(( (END - START) / 1000000 ))
    
    # Parse response
    COMPLETION_TOKENS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('usage',{}).get('completion_tokens',0))" 2>/dev/null)
    PROMPT_TOKENS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('usage',{}).get('prompt_tokens',0))" 2>/dev/null)
    REASONING_LEN=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); r=d['choices'][0]['message'].get('reasoning',''); print(len(r) if r else 0)" 2>/dev/null)
    CONTENT_LEN=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d['choices'][0]['message'].get('content',''); print(len(c) if c else 0)" 2>/dev/null)
    FINISH=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0].get('finish_reason','?'))" 2>/dev/null)
    
    SPEED=$(python3 -c "print(f'{$COMPLETION_TOKENS / ($WALL_MS / 1000):.1f}')" 2>/dev/null)
    
    echo "  Prompt: ${PROMPT_TOKENS} tokens"
    echo "  Completion: ${COMPLETION_TOKENS} tokens"
    echo "  Reasoning: ${REASONING_LEN} chars"
    echo "  Content: ${CONTENT_LEN} chars"
    echo "  Finish: ${FINISH}"
    echo "  Wall time: ${WALL_MS}ms"
    echo "  Speed: ${SPEED} tok/s"
    echo ""
}

# Test 1: Short response
run_test 50 "Short" "What is 2+2? Answer in one word."

# Test 2: Medium response
run_test 200 "Medium" "Explain what a transformer neural network is in 3 sentences."

# Test 3: Long response
run_test 500 "Long" "Write a detailed technical analysis of how transformer attention mechanisms work."

# Test 4: With tool calls
echo "--- Tool Call Test ---"
curl -s http://localhost:18020/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen3.8-27b",
        "messages": [{"role": "user", "content": "Read the file /tmp/test.txt"}],
        "max_tokens": 200,
        "tools": [{"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]
    }' 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
msg = d['choices'][0]['message']
tc = msg.get('tool_calls', [])
print(f'  Tool calls: {len(tc)}')
if tc:
    print(f'  Function: {tc[0][\"function\"][\"name\"]}')
    print(f'  Args: {tc[0][\"function\"][\"arguments\"]}')
print(f'  Content: {msg.get(\"content\",\"(null)\")}')
print(f'  Reasoning: {(msg.get(\"reasoning\") or \"\")[:100]}')
print(f'  Finish: {d[\"choices\"][0].get(\"finish_reason\")}')
" 2>/dev/null
echo ""

echo "=== Done ==="
