/**
 * Copie les assets du dashboard web vers le dossier www/ de Capacitor
 */
const fs   = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', '..', 'saas', 'frontend');
const DST = path.join(__dirname, '..', 'www');

function copyDir(src, dst) {
  if (!fs.existsSync(dst)) fs.mkdirSync(dst, { recursive: true });
  for (const file of fs.readdirSync(src)) {
    const srcPath = path.join(src, file);
    const dstPath = path.join(dst, file);
    if (fs.statSync(srcPath).isDirectory()) {
      copyDir(srcPath, dstPath);
    } else {
      fs.copyFileSync(srcPath, dstPath);
    }
  }
}

// Copier le dashboard
copyDir(SRC, DST);

// Injecter le plugin Capacitor dans le HTML
const htmlPath = path.join(DST, 'dashboard.html');
if (fs.existsSync(htmlPath)) {
  let html = fs.readFileSync(htmlPath, 'utf8');
  if (!html.includes('capacitor.js')) {
    html = html.replace(
      '<script src="https://cdn.jsdelivr.net',
      '<script src="/capacitor.js"></script>\n  <script src="https://cdn.jsdelivr.net'
    );
    fs.writeFileSync(htmlPath, html);
  }
}

console.log('✅ Assets copiés vers www/');
console.log('   Prochaine étape : npx cap sync android');
