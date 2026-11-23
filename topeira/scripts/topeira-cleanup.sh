#!/usr/bin/env bash
#
# topeira-cleanup.sh — limpeza assistida macOS, Tier B + pendências do run 2026-05-24
#
# Rode com Full Disk Access para o Terminal:
#   System Settings → Privacy & Security → Full Disk Access → adicionar Terminal.app
# Senão, o mediaanalysisd cache (3.5 GB) continua bloqueado por TCC silenciosamente.
#
# Convenção: confirma por categoria, mede delta real, anota em log canônico.
# Red lines respeitadas: Spotify, Codex CLI runtimes, Claude Desktop caches,
#                       WhatsApp, Mail, ML stack — NUNCA tocados.
#
# Uso:
#   bash scripts/topeira-cleanup.sh           # interactive
#   bash scripts/topeira-cleanup.sh --dry-run # só lista, não toca
#   bash scripts/topeira-cleanup.sh --yes     # auto-confirma (use com cuidado)

set -uo pipefail

DRY_RUN=0
AUTO_YES=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    --yes|-y)     AUTO_YES=1 ;;
    --help|-h)
      sed -n '2,18p' "$0"
      exit 0 ;;
  esac
done

LOG="${TOPEIRA_LOG:-${HOME}/.local/state/topeira/topeira_log.md}"
TS="$(date '+%Y-%m-%d %H:%M')"
NOW_EPOCH=$(date +%s)
RUN_LABEL="Run #2 (terminal Tier B + pendências)"

# ── helpers ──────────────────────────────────────────────────────────────
free_kb() { df -k / | awk 'NR==2 {print $4}'; }
free_human() { df -H / | awk 'NR==2 {print $4 " livres ("$5" used)"}'; }
hr() { printf '\n%s\n' "────────────────────────────────────────────────────────"; }
run_maybe_timeout() {
  local seconds="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$seconds" "$@"
  else
    "$@"
  fi
}

confirm() {
  # confirm "msg" → 0 yes, 1 no
  if [[ $AUTO_YES -eq 1 ]]; then return 0; fi
  if [[ $DRY_RUN -eq 1 ]]; then return 1; fi
  printf '%s [y/N] ' "$1"
  read -r ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

du_safe() {
  # du -sh com timeout — Containers pode travar por TCC
  local p="$1"
  [[ -e "$p" ]] || { echo "(missing)"; return; }
  run_maybe_timeout 5 du -sh "$p" 2>/dev/null | awk '{print $1}' || echo "(TCC?)"
}

clean_category() {
  # clean_category "label" "tier" path1 path2 ...
  local label="$1"; shift
  local tier="$1"; shift
  local before after delta
  local sizes=()

  hr
  echo "▶ $label (Tier $tier)"
  for p in "$@"; do
    if [[ -e "$p" ]]; then
      local sz; sz=$(du_safe "$p")
      sizes+=("  $sz  $p")
    else
      sizes+=("  (missing)  $p")
    fi
  done
  printf '%s\n' "${sizes[@]}"

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  → dry-run, sem deletar"
    return
  fi

  if ! confirm "  Limpar?"; then
    echo "  ⏭  pulado"
    SKIPPED+=("$label")
    return
  fi

  before=$(free_kb)
  for p in "$@"; do
    [[ -e "$p" ]] || continue
    /bin/rm -rf -- "$p"/* 2>/dev/null || true
    /bin/rm -rf -- "$p" 2>/dev/null || true
  done
  after=$(free_kb)
  delta=$(( after - before ))
  echo "  ✅ Δ free: $(awk -v k=$delta 'BEGIN{printf "%.1f MB\n", k/1024}')"
  DELTAS+=("$label|$tier|$delta")
}

# ── baseline ─────────────────────────────────────────────────────────────
echo "═══ Topeira $TS — $RUN_LABEL ═══"
echo "Modo: $([ $DRY_RUN -eq 1 ] && echo "DRY-RUN" || ([ $AUTO_YES -eq 1 ] && echo "AUTO-YES" || echo "interactive"))"
echo "Baseline: $(free_human)"
echo "Load avg: $(uptime | awk -F'load averages?:' '{print $2}')"

# TCC probe — testa Full Disk Access ANTES de prometer cleanup mediaanalysisd
TCC_OK=0
if [[ -d "$HOME/Library/Containers/com.apple.mediaanalysisd/Data/Library/Caches" ]]; then
  if run_maybe_timeout 3 ls "$HOME/Library/Containers/com.apple.mediaanalysisd/Data/Library/Caches" >/dev/null 2>&1; then
    TCC_OK=1
  fi
fi
if [[ $TCC_OK -eq 1 ]]; then
  echo "TCC: ✅ Full Disk Access detectado — mediaanalysisd cleanup disponível"
else
  echo "TCC: ⚠️  Sem Full Disk Access — mediaanalysisd 3.5 GB ficará bloqueado."
  echo "    Para destravar: System Settings → Privacy & Security → Full Disk Access → adicionar Terminal.app"
  echo "    Depois feche e reabra o Terminal, e rode este script de novo."
fi

# Process checks — não limpar caches de apps rodando
RUNNING=()
check_app() {
  # check_app "label" "pgrep pattern"
  if pgrep -lf "$2" 2>/dev/null | grep -qv "$0"; then
    RUNNING+=("$1")
  fi
}
check_app "Comet"            "/Applications/Comet.app"
check_app "Codex.app"        "/Applications/Codex.app/Contents/MacOS/Codex"
check_app "Claude Desktop"   "/Applications/Claude.app/Contents/MacOS/Claude"
check_app "Antigravity"      "Antigravity.app"
check_app "Steam"            "/Applications/Steam.app"
check_app "Termius"          "/Applications/Termius.app"
check_app "VS Code / Cursor" "/Applications/Visual Studio Code.app|/Applications/Cursor.app"
check_app "Zed"              "/Applications/Zed.app"

echo "Apps rodando (caches dele serão pulados): ${RUNNING[*]:-nenhum}"

DELTAS=()
SKIPPED=()

# ── Tier B: mediaanalysisd cache (TCC required) ──────────────────────────
if [[ $TCC_OK -eq 1 ]]; then
  if ! pgrep -x mediaanalysisd >/dev/null 2>&1; then
    clean_category "mediaanalysisd cache (~3.5 GB)" "B" \
      "$HOME/Library/Containers/com.apple.mediaanalysisd/Data/Library/Caches" \
      "$HOME/Library/Containers/com.apple.mediaanalysisd/Data/tmp/Pissarro"
  else
    hr
    echo "▶ mediaanalysisd cache: PULADO (processo ativo — regen rápido)"
  fi
fi

# ── Tier A pendências (apps fechados only) ───────────────────────────────

# Comet cache (1.0 GB) — só se Comet fechado
if ! printf '%s\n' "${RUNNING[@]}" | grep -qx "Comet"; then
  clean_category "Comet browser cache (~1.0 GB)" "A" \
    "$HOME/Library/Caches/Comet/Default"
else
  hr
  echo "▶ Comet cache: PULADO (Comet rodando — feche o app e re-rode)"
  SKIPPED+=("Comet cache")
fi

# Codex.app caches (Codex Computer Use desktop app, ≠ Codex CLI runtimes)
if ! printf '%s\n' "${RUNNING[@]}" | grep -qx "Codex.app"; then
  clean_category "Codex.app caches (~25 MB)" "A" \
    "$HOME/Library/Application Support/Codex/Cache" \
    "$HOME/Library/Application Support/Codex/Code Cache" \
    "$HOME/Library/Application Support/Codex/GPUCache" \
    "$HOME/Library/Application Support/Codex/DawnGraphiteCache" \
    "$HOME/Library/Application Support/Codex/DawnWebGPUCache"
else
  hr
  echo "▶ Codex.app caches: PULADO (Codex.app rodando — feche e re-rode)"
  SKIPPED+=("Codex.app caches")
fi

# ── Browser leftovers ─────────────────────────────────────────────────────
clean_category "DiagnosticReports (crash dumps antigos)" "A" \
  "$HOME/Library/Logs/DiagnosticReports"

# Mole canon recommendations
clean_category "Comet logs (separados do cache)" "A" \
  "$HOME/Library/Logs/Comet"

# ── /private/var/folders cleanup (only -atime +30, low risk) ─────────────
hr
echo "▶ /private/var/folders — temp files >30 dias (read-only inventory primeiro)"
TMP_OLD_BYTES=$(/usr/bin/find /private/var/folders -type f -atime +30 -size +1M 2>/dev/null | xargs -I{} stat -f%z "{}" 2>/dev/null | awk '{s+=$1} END {print s+0}')
TMP_OLD_MB=$(( TMP_OLD_BYTES / 1024 / 1024 ))
echo "  Encontrado: ${TMP_OLD_MB} MB em files >30d sem acesso, >1 MB cada"
if [[ $TMP_OLD_MB -gt 50 ]] && confirm "  Limpar? (find ... -atime +30 -delete)"; then
  before=$(free_kb)
  /usr/bin/find /private/var/folders -type f -atime +30 -size +1M -delete 2>/dev/null
  after=$(free_kb)
  delta=$(( after - before ))
  echo "  ✅ Δ free: $(awk -v k=$delta 'BEGIN{printf "%.1f MB\n", k/1024}')"
  DELTAS+=("/private/var/folders old|A|$delta")
fi

# ── Orphan dotfiles ───────────────────────────────────────────────────────
hr
echo "▶ Orphan dotfiles (Mole detectou; revisão manual)"
for d in "$HOME/.playwright-gdrive-profile" "$HOME/.redhat"; do
  if [[ -e "$d" ]]; then
    sz=$(du_safe "$d")
    age_days=$(( ( $(date +%s) - $(stat -f %m "$d") ) / 86400 ))
    echo "  $sz  $d  (last touch: ${age_days}d ago)"
  fi
done
echo "  → não removo automaticamente. Se confirmar:"
echo "    rm -rf ~/.playwright-gdrive-profile  # 48.8 MB, 74d old"
echo "    rm -rf ~/.redhat                     # 4 KB, 65d old"

# ── Summary ──────────────────────────────────────────────────────────────
hr
TOTAL_KB=0
echo "═══ RESUMO ═══"
echo "Final: $(free_human)"
echo ""
echo "Deltas:"
if [[ ${#DELTAS[@]} -eq 0 ]]; then
  echo "  (nenhuma categoria limpa)"
else
  for entry in "${DELTAS[@]}"; do
    IFS='|' read -r label tier kb <<< "$entry"
    TOTAL_KB=$(( TOTAL_KB + kb ))
    printf "  [Tier %s] %s: +%.1f MB\n" "$tier" "$label" "$(awk -v k=$kb 'BEGIN{print k/1024}')"
  done
fi
TOTAL_GB=$(awk -v k=$TOTAL_KB 'BEGIN{printf "%.2f", k/1024/1024}')
echo ""
echo "TOTAL: +${TOTAL_GB} GB recuperados nesta run"
if [[ ${#SKIPPED[@]} -gt 0 ]]; then
  echo ""
  echo "Pulados (apps rodando ou sem confirmação):"
  printf '  - %s\n' "${SKIPPED[@]}"
fi

# ── Append ao log canônico ───────────────────────────────────────────────
if [[ $DRY_RUN -eq 0 ]] && [[ $TOTAL_KB -gt 0 ]]; then
  mkdir -p "$(dirname "$LOG")"
  {
    echo ""
    echo "---"
    echo ""
    echo "## $TS — $RUN_LABEL"
    echo ""
    echo "**Runtime**: bash script (\`scripts/topeira-cleanup.sh\`) rodado pelo usuário no Terminal"
    echo "**TCC**: $([ $TCC_OK -eq 1 ] && echo "✅ Full Disk Access" || echo "❌ sem FDA — mediaanalysisd pulado")"
    echo "**Apps rodando**: ${RUNNING[*]:-nenhum}"
    echo ""
    echo "### Deltas"
    echo ""
    for entry in "${DELTAS[@]}"; do
      IFS='|' read -r label tier kb <<< "$entry"
      printf -- "- [Tier %s] %s: +%.1f MB\n" "$tier" "$label" "$(awk -v k=$kb 'BEGIN{print k/1024}')"
    done
    echo ""
    echo "**Total**: +${TOTAL_GB} GB"
    echo ""
    if [[ ${#SKIPPED[@]} -gt 0 ]]; then
      echo "### Pulados"
      printf -- "- %s\n" "${SKIPPED[@]}"
      echo ""
    fi
  } >> "$LOG"
  echo ""
  echo "📝 Log atualizado: $LOG"
fi
