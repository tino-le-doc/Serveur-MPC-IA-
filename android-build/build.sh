#!/usr/bin/env bash
# ============================================================
# Script de build APK — MCP IA Android
# Requires: Java, aapt, dalvik-exchange (dx), zipalign, apksigner
# ============================================================
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$BASE_DIR/build"
OUT_DIR="$BASE_DIR/output"
ANDROID_JAR="/usr/lib/android-sdk/platforms/android-23/android.jar"
MAIN_JAVA="$BASE_DIR/src/main/java"
MANIFEST="$BASE_DIR/src/main/AndroidManifest.xml"
RES_DIR="$BASE_DIR/src/main/res"
ASSETS_DIR="$BASE_DIR/src/main/assets"
PACKAGE="com.mcpia.app"
APK_NAME="MCP-IA-1.0.0"

echo "=== Build APK MCP IA ==="
echo ""

# Nettoyage
rm -rf "$BUILD_DIR" "$OUT_DIR"
mkdir -p "$BUILD_DIR"/{gen,obj,dex,apk} "$OUT_DIR"

# ── Étape 1 : Générer R.java via aapt ────────────────────────────────────────
echo "→ Étape 1/6 : Génération R.java (aapt)..."
aapt package \
  -f -m \
  -J "$BUILD_DIR/gen" \
  -M "$MANIFEST" \
  -S "$RES_DIR" \
  -I "$ANDROID_JAR" \
  2>&1
echo "   ✓ R.java généré"

# ── Étape 2 : Compilation Java ────────────────────────────────────────────────
echo "→ Étape 2/6 : Compilation Java..."
find "$MAIN_JAVA" "$BUILD_DIR/gen" -name "*.java" > "$BUILD_DIR/sources.txt"
javac \
  -source 1.8 \
  -target 1.8 \
  -bootclasspath "$ANDROID_JAR" \
  -classpath "$BUILD_DIR/obj" \
  -d "$BUILD_DIR/obj" \
  @"$BUILD_DIR/sources.txt" \
  2>&1
echo "   ✓ Classes compilées"

# ── Étape 3 : Conversion en DEX ──────────────────────────────────────────────
echo "→ Étape 3/6 : Conversion en DEX (dalvik-exchange)..."
dalvik-exchange \
  --dex \
  --output="$BUILD_DIR/dex/classes.dex" \
  "$BUILD_DIR/obj" \
  2>&1
echo "   ✓ classes.dex créé"

# ── Étape 4 : Packaging APK non-signé ────────────────────────────────────────
echo "→ Étape 4/6 : Packaging APK..."
UNSIGNED_APK="$BUILD_DIR/apk/${APK_NAME}-unsigned.apk"
aapt package \
  -f \
  -M "$MANIFEST" \
  -S "$RES_DIR" \
  -A "$ASSETS_DIR" \
  -I "$ANDROID_JAR" \
  -F "$UNSIGNED_APK" \
  2>&1

# Ajouter classes.dex dans le zip
cd "$BUILD_DIR/apk"
cp "$BUILD_DIR/dex/classes.dex" .
zip -qj "$UNSIGNED_APK" classes.dex
cd "$BASE_DIR"
echo "   ✓ APK packagé"

# ── Étape 5 : Génération de la keystore de signature ─────────────────────────
echo "→ Étape 5/6 : Signature APK..."
KEYSTORE="$BUILD_DIR/mcpia.keystore"
if [ ! -f "$KEYSTORE" ]; then
  keytool -genkey -v \
    -keystore "$KEYSTORE" \
    -alias mcpia \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storepass mcpia2025 \
    -keypass mcpia2025 \
    -dname "CN=MCP IA, OU=Dev, O=MCPIA, L=Paris, ST=IDF, C=FR" \
    2>&1 | grep -v "^Warning"
fi

SIGNED_APK="$BUILD_DIR/apk/${APK_NAME}-signed.apk"
jarsigner \
  -keystore "$KEYSTORE" \
  -storepass mcpia2025 \
  -keypass mcpia2025 \
  -signedjar "$SIGNED_APK" \
  "$UNSIGNED_APK" \
  mcpia \
  2>&1

echo "   ✓ APK signé"

# ── Étape 6 : Zipalign ───────────────────────────────────────────────────────
echo "→ Étape 6/6 : Zipalign..."
FINAL_APK="$OUT_DIR/${APK_NAME}.apk"
zipalign -v 4 "$SIGNED_APK" "$FINAL_APK" 2>&1 | grep -E "Verifying|zip aligned|^$" | head -5

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅  BUILD RÉUSSI                                ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  APK : output/${APK_NAME}.apk                    ║"
SIZE=$(ls -lh "$FINAL_APK" | awk '{print $5}')
echo "║  Taille : $SIZE                                   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Pour installer sur un téléphone connecté :"
echo "  adb install \"$FINAL_APK\""
