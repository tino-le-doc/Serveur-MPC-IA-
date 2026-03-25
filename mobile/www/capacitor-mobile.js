/**
 * Intégration Capacitor pour les fonctionnalités natives Android/iOS
 * Notifications push, vibration, statut réseau, etc.
 */

// Détection de l'environnement Capacitor
const isNative = typeof window !== 'undefined' && window.Capacitor?.isNativePlatform?.();
const platform = window.Capacitor?.getPlatform?.() || 'web';

// ─── Notifications Push ───────────────────────
async function initPushNotifications() {
  if (!isNative) return;
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications');

    const perm = await PushNotifications.checkPermissions();
    if (perm.receive !== 'granted') {
      const req = await PushNotifications.requestPermissions();
      if (req.receive !== 'granted') return;
    }

    await PushNotifications.register();

    PushNotifications.addListener('registration', (token) => {
      console.log('[Push] Token FCM :', token.value);
      localStorage.setItem('fcm_token', token.value);
    });

    PushNotifications.addListener('pushNotificationReceived', (notification) => {
      console.log('[Push] Notification reçue :', notification);
      // Afficher une bannière dans l'app
      showInAppNotification(notification.title, notification.body);
    });

    PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      const data = action.notification.data;
      if (data?.page) navigateToPage(data.page);
    });

  } catch (e) {
    console.warn('[Push] Non disponible :', e);
  }
}

// ─── Réseau ───────────────────────────────────
async function initNetworkMonitor() {
  if (!isNative) return;
  try {
    const { Network } = await import('@capacitor/network');
    const status = await Network.getStatus();
    updateNetworkUI(status.connected);

    Network.addListener('networkStatusChange', (s) => {
      updateNetworkUI(s.connected);
    });
  } catch (e) {}
}

function updateNetworkUI(connected) {
  const indicator = document.getElementById('networkIndicator');
  if (!indicator) return;
  indicator.style.background = connected ? 'var(--accent2)' : 'var(--danger)';
  indicator.title = connected ? 'En ligne' : 'Hors ligne';
}

// ─── Haptics (vibration) ─────────────────────
async function hapticFeedback(style = 'medium') {
  if (!isNative) return;
  try {
    const { Haptics, ImpactStyle } = await import('@capacitor/haptics');
    const s = { light: ImpactStyle.Light, medium: ImpactStyle.Medium, heavy: ImpactStyle.Heavy };
    await Haptics.impact({ style: s[style] || ImpactStyle.Medium });
  } catch (e) {}
}

// ─── Status Bar ───────────────────────────────
async function initStatusBar() {
  if (!isNative) return;
  try {
    const { StatusBar, Style } = await import('@capacitor/status-bar');
    await StatusBar.setStyle({ style: Style.Dark });
    await StatusBar.setBackgroundColor({ color: '#0f1117' });
  } catch (e) {}
}

// ─── Splash Screen ───────────────────────────
async function hideSplash() {
  if (!isNative) return;
  try {
    const { SplashScreen } = await import('@capacitor/splash-screen');
    await SplashScreen.hide({ fadeOutDuration: 300 });
  } catch (e) {}
}

// ─── Notification in-app ─────────────────────
function showInAppNotification(title, body) {
  const el = document.createElement('div');
  el.style.cssText = `
    position:fixed;top:1rem;right:1rem;left:1rem;
    background:#1a1d27;border:1px solid #6c63ff;border-radius:12px;
    padding:.8rem 1rem;box-shadow:0 8px 32px rgba(0,0,0,.5);
    z-index:99999;animation:slideIn .3s ease;
  `;
  el.innerHTML = `<strong style="color:#e2e8f0">${title || 'MCP IA'}</strong>
    <p style="color:#64748b;font-size:.85rem;margin-top:.2rem">${body || ''}</p>`;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 5000);
  el.addEventListener('click', () => el.remove());
}

function navigateToPage(page) {
  if (window.showPage) window.showPage(page);
}

// ─── Init ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  hideSplash();
  initStatusBar();
  initNetworkMonitor();
  initPushNotifications();
  console.log(`[Capacitor] Plateforme : ${platform}, Natif : ${isNative}`);
});

// Exposer les helpers globalement
window.nativeApp = { hapticFeedback, showInAppNotification, platform, isNative };
