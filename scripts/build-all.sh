#!/bin/bash
# ═══════════════════════════════════════════════
# MCP IA — Script de build toutes plateformes
# ═══════════════════════════════════════════════
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}ℹ $1${NC}"; }
ok()    { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; exit 1; }

echo -e "${BLUE}
╔══════════════════════════════╗
║     MCP IA — Build System    ║
╚══════════════════════════════╝${NC}"

# ─── Vérifier Python ─────────────────────────
check_python() {
  if command -v python3 &>/dev/null; then
    PYTHON=python3
  elif command -v python &>/dev/null; then
    PYTHON=python
  else
    error "Python 3.10+ requis mais non trouvé"
  fi
  PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  info "Python $PY_VER détecté"
}

# ─── Vérifier Node.js ────────────────────────
check_node() {
  if ! command -v node &>/dev/null; then
    warn "Node.js non détecté — builds desktop/mobile désactivés"
    return 1
  fi
  NODE_VER=$(node --version)
  info "Node.js $NODE_VER détecté"
  return 0
}

# ─── Installer dépendances Python ────────────
install_python_deps() {
  info "Installation des dépendances Python (SaaS)..."
  $PYTHON -m pip install -r "$ROOT/saas/requirements.txt" -q
  ok "Dépendances Python installées"
}

# ─── Build Desktop (Electron) ────────────────
build_desktop() {
  if ! check_node; then return; fi

  info "Installation des dépendances Electron..."
  cd "$ROOT/desktop"
  npm install -q

  TARGET="${1:-}"
  if [ "$(uname)" = "Darwin" ] || [ "$TARGET" = "mac" ]; then
    info "Build macOS (.dmg)..."
    npm run build:mac
    ok "Build Mac créé dans desktop/dist/"
  fi
  if [ "$(uname)" = "Linux" ] || [ "$TARGET" = "win" ]; then
    info "Build Windows (.exe) via Wine..."
    npm run build:win || warn "Build Windows nécessite Wine sur Linux/Mac"
  fi

  cd "$ROOT"
}

# ─── Build Android (Capacitor) ───────────────
build_android() {
  if ! check_node; then return; fi
  if ! command -v java &>/dev/null; then
    warn "Java non détecté — build Android désactivé (requis : JDK 17+)"
    return
  fi
  if [ -z "$ANDROID_HOME" ] && [ -z "$ANDROID_SDK_ROOT" ]; then
    warn "ANDROID_HOME non défini — build Android désactivé"
    return
  fi

  info "Build Android (Capacitor)..."
  cd "$ROOT/mobile"
  npm install -q
  node scripts/copy-assets.js

  # Vérifier si le projet Android existe déjà
  if [ ! -d "android" ]; then
    info "Initialisation du projet Android..."
    npx cap add android
  fi

  npx cap sync android

  if [ -f "android/gradlew" ]; then
    cd android
    chmod +x gradlew
    ./gradlew assembleRelease 2>/dev/null || ./gradlew assembleDebug
    ok "APK Android créé dans mobile/android/app/build/outputs/apk/"
  fi

  cd "$ROOT"
}

# ─── Préparer PWA ────────────────────────────
prepare_pwa() {
  info "Préparation PWA..."
  # Vérifier que les fichiers PWA sont en place
  for f in manifest.json sw.js; do
    if [ -f "$ROOT/saas/frontend/$f" ]; then
      ok "PWA : $f présent"
    else
      warn "PWA : $f manquant"
    fi
  done
}

# ─── Main ─────────────────────────────────────
check_python
install_python_deps
prepare_pwa

case "${1:-all}" in
  desktop) build_desktop "${2:-}" ;;
  android) build_android ;;
  all)
    build_desktop
    build_android
    ;;
  *)
    echo "Usage: $0 [all|desktop [mac|win]|android]"
    ;;
esac

echo ""
echo -e "${GREEN}═══════════════════════════════════
  Build terminé !

  📁 Desktop  : desktop/dist/
  📱 Android  : mobile/android/app/build/outputs/apk/
  🌐 PWA      : Lancez le serveur SaaS et ouvrez sur mobile
═══════════════════════════════════${NC}"
