#!/usr/bin/env bash
# Compara runs por tokens GERADOS POR REQUISICAO.
# Fonte correta: linha print_timing "eval time = X ms / N tokens" (uma por requisicao).
# NAO usar n_decoded: e logado a cada token e mede progresso, nao total.
cd /root/qwen3
stats() { awk '{a[NR]=$1;s+=$1; if($1>=8100)e++} END{if(NR==0){print "  sem dados"; exit}
  printf "  req: %5d | mediana: %5d | media: %5d | max: %5d | >=8100: %d\n",NR,a[int(NR/2)],s/NR,a[NR],e+0}'; }
pick() { grep -a 'print_timing' | grep -av 'prompt eval time' | grep -aoE 'eval time = *[0-9.]+ ms / *[0-9]+ tokens' | grep -oE '/ *[0-9]+' | tr -d '/ '; }
for f in data/logs/server.log.1 data/logs/server.log; do
  [ -f "$f" ] || continue
  mapfile -t LNS < <(grep -an 'Reasoning :' "$f" | cut -d: -f1)
  for i in "${!LNS[@]}"; do
    ln=${LNS[$i]}; nxt=${LNS[$((i+1))]:-999999999}
    echo "[$(basename $f):$ln] $(sed -n "$((ln-3))p" "$f" | grep -o 'temp=[0-9.]* top_p=[0-9.]*') | $(sed -n "${ln}p" "$f" | sed 's/.*Reasoning : //')"
    awk -v a="$ln" -v b="$nxt" 'NR>a && NR<b' "$f" | pick | sort -n | stats
  done
done
