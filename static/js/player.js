(function () {
    const body = document.body;
    const statusUrl = body.dataset.statusUrl;
    const root = document.getElementById("player-root");
    const backdropEl = document.getElementById("player-backdrop");
    const overlay = document.getElementById("player-overlay");
    const imageEls = [
        document.getElementById("player-image-a"),
        document.getElementById("player-image-b"),
    ].filter(Boolean);
    const videoEl = document.getElementById("player-video");

    const LANDSCAPE_COVER_THRESHOLD = 0.14;

    let playlist = [];
    let currentIndex = 0;
    let timer = null;
    let activeAlbumId = null;
    let playlistKey = null;
    let activeImageIndex = -1;
    let imageRequestToken = 0;

    function setOverlay(text) {
        overlay.textContent = text;
    }

    function clearNextTimer() {
        if (timer) {
            clearTimeout(timer);
            timer = null;
        }
    }

    function scheduleNext(ms) {
        clearNextTimer();
        timer = setTimeout(playNext, ms);
    }

    function hideAllImages() {
        imageEls.forEach((img) => {
            img.classList.remove("visible");
            img.classList.add("hidden");
        });
        activeImageIndex = -1;
    }

    function hideVideo() {
        videoEl.onended = null;
        videoEl.pause();
        videoEl.classList.remove("visible");
        videoEl.classList.add("hidden");
        videoEl.removeAttribute("src");
        videoEl.load();
    }

    function clearImageModeClasses() {
        root.classList.remove("image-landscape-cover", "image-landscape-contain", "image-portrait");
    }

    function chooseImageMode(width, height) {
        if (!width || !height || width < height) {
            return "image-portrait";
        }

        const screenAspect = window.innerWidth / Math.max(1, window.innerHeight);
        const imageAspect = width / height;
        const normalizedDelta = Math.abs(imageAspect - screenAspect) / Math.max(screenAspect, 0.01);

        if (normalizedDelta <= LANDSCAPE_COVER_THRESHOLD) {
            return "image-landscape-cover";
        }
        return "image-landscape-contain";
    }

    function activateImage(targetEl) {
        imageEls.forEach((img, index) => {
            const isTarget = img === targetEl;
            img.classList.toggle("visible", isTarget);
            img.classList.toggle("hidden", !isTarget);
            if (isTarget) {
                activeImageIndex = index;
            }
        });
    }

    function getNextImageEl() {
        if (!imageEls.length) {
            return null;
        }
        if (imageEls.length === 1 || activeImageIndex < 0) {
            return imageEls[0];
        }
        return imageEls[activeImageIndex === 0 ? 1 : 0];
    }

    function preloadImage(url) {
        return new Promise((resolve, reject) => {
            const probe = new Image();
            probe.decoding = "async";
            probe.onload = () => resolve(probe);
            probe.onerror = () => reject(new Error("image load failed"));
            probe.src = url;
        });
    }

    function prefetchUpcomingPhoto() {
        if (!playlist.length) {
            return;
        }
        const nextItem = playlist[currentIndex % playlist.length];
        if (!nextItem || nextItem.type !== "photo" || !nextItem.normalized_url) {
            return;
        }
        const prefetch = new Image();
        prefetch.src = nextItem.normalized_url;
    }

    async function showImage(item) {
        const url = item.normalized_url;
        if (!url) {
            return false;
        }

        const requestId = ++imageRequestToken;
        const backdropUrl = item.thumb_url || url;

        root.classList.add("showing-image");
        root.classList.remove("showing-video");
        clearImageModeClasses();
        hideVideo();

        if (backdropEl) {
            backdropEl.style.backgroundImage = `url("${backdropUrl}")`;
        }

        try {
            const probe = await preloadImage(url);
            if (requestId !== imageRequestToken) {
                return false;
            }

            const target = getNextImageEl();
            if (!target) {
                return false;
            }

            target.src = url;
            const modeClass = chooseImageMode(probe.naturalWidth, probe.naturalHeight);
            clearImageModeClasses();
            root.classList.add(modeClass);
            activateImage(target);
            return true;
        } catch (_err) {
            if (requestId === imageRequestToken) {
                setOverlay("Failed to load image");
            }
            return false;
        }
    }

    function showVideo(url) {
        imageRequestToken += 1;
        clearNextTimer();

        root.classList.add("showing-video");
        root.classList.remove("showing-image");
        clearImageModeClasses();

        if (backdropEl) {
            backdropEl.style.backgroundImage = "none";
        }

        hideAllImages();

        videoEl.src = url;
        videoEl.classList.remove("hidden");
        videoEl.classList.add("visible");
        videoEl.play().catch(() => {
            setOverlay("Video autoplay blocked; tap to continue");
        });
        videoEl.onended = () => playNext();
    }

    function playNext() {
        if (!playlist.length) {
            setOverlay("Waiting for an active album...");
            return;
        }

        const item = playlist[currentIndex % playlist.length];
        currentIndex += 1;

        if (item.type === "video") {
            setOverlay("");
            showVideo(item.normalized_url);
            return;
        }

        setOverlay("");
        showImage(item).then((shown) => {
            if (!shown) {
                return;
            }
            prefetchUpcomingPhoto();
            const durationMs = Math.max(1, Number(item.duration_seconds || 8)) * 1000;
            scheduleNext(durationMs);
        });
    }

    async function fetchJson(url, options) {
        const res = await fetch(url, options);
        if (!res.ok) {
            throw new Error("Request failed");
        }
        return res.json();
    }

    function maybeShuffle(items, doShuffle) {
        if (!doShuffle) {
            return items;
        }
        const shuffled = [...items];
        for (let i = shuffled.length - 1; i > 0; i -= 1) {
            const j = Math.floor(Math.random() * (i + 1));
            [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
        }
        return shuffled;
    }

    function buildPlaylistKey(activeId, payload) {
        const items = payload.items || [];
        const settings = payload.settings || {};
        const itemKey = items
            .map((item) => `${item.media_id}:${item.type}:${item.duration_seconds || ""}`)
            .join("|");
        return `${activeId}|${settings.shuffle ? "1" : "0"}|${itemKey}`;
    }

    async function refreshPlaylist() {
        try {
            const status = await fetchJson(statusUrl);
            if (!status.active_album_id) {
                playlist = [];
                activeAlbumId = null;
                playlistKey = null;
                imageRequestToken += 1;
                clearNextTimer();
                root.classList.remove("showing-image", "showing-video");
                clearImageModeClasses();
                hideAllImages();
                hideVideo();
                if (backdropEl) {
                    backdropEl.style.backgroundImage = "none";
                }
                setOverlay("No active album selected");
                return;
            }

            const payload = await fetchJson(`/api/albums/${status.active_album_id}/playlist`);
            const nextKey = buildPlaylistKey(status.active_album_id, payload);
            if (nextKey === playlistKey && playlist.length) {
                return;
            }

            playlist = maybeShuffle(payload.items || [], Boolean(payload.settings && payload.settings.shuffle));
            activeAlbumId = status.active_album_id;
            playlistKey = nextKey;
            currentIndex = 0;
            clearNextTimer();

            if (!playlist.length) {
                setOverlay("Active album has no ready media");
                return;
            }

            playNext();
        } catch (_err) {
            setOverlay("Player failed to load playlist");
        }
    }

    refreshPlaylist();
    setInterval(refreshPlaylist, 5000);
})();
