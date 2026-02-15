(function () {
    function registerServiceWorker() {
        if (!('serviceWorker' in navigator)) {
            return;
        }
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js').catch(() => {});
        });
    }

    function showIosInstallTip() {
        const tip = document.getElementById('pwa-install-tip');
        const dismiss = document.getElementById('install-tip-dismiss');
        if (!tip || !dismiss) {
            return;
        }

        const ua = window.navigator.userAgent || '';
        const isIos = /iPhone|iPad|iPod/.test(ua);
        const isSafari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
        const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
        const dismissed = window.localStorage.getItem('vframe_install_tip_dismissed') === '1';

        if (isIos && isSafari && !isStandalone && !dismissed) {
            tip.classList.remove('hidden');
        }

        dismiss.addEventListener('click', () => {
            tip.classList.add('hidden');
            window.localStorage.setItem('vframe_install_tip_dismissed', '1');
        });
    }

    registerServiceWorker();
    showIosInstallTip();
})();
