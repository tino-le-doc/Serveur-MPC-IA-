#!/bin/bash
# Script d'installation des dépendances pour le build desktop

set -e
echo "📦 Installation des dépendances Electron..."
cd "$(dirname "$0")"
npm install

echo ""
echo "📦 Installation des dépendances Python (SaaS backend)..."
cd ../saas
pip install -r requirements.txt

echo ""
echo "✅ Prêt ! Pour lancer en dev :"
echo "   cd desktop && npm start"
echo ""
echo "Pour builder l'application :"
echo "   npm run build:mac   # → .dmg pour Mac"
echo "   npm run build:win   # → .exe pour Windows"
