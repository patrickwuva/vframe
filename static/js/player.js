(function () {
    const body = document.body;
    const statusUrl = body.dataset.statusUrl;
    const root = document.getElementById("player-root");
    const backdropEls = [
        document.getElementById("player-backdrop-a"),
        document.getElementById("player-backdrop-b"),
    ].filter(Boolean);
    const overlay = document.getElementById("player-overlay");
    const imageEls = [
        document.getElementById("player-image-a"),
        document.getElementById("player-image-b"),
    ].filter(Boolean);
    const videoEl = document.getElementById("player-video");

    let playlist = [];
    let currentIndex = 0;
    let timer = null;
    let playlistKey = null;
    let activeImageIndex = -1;
    let activeBackdropIndex = -1;
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

    function clearImageModeClasses() {
        root.classList.remove("image-landscape-cover", "image-landscape-contain", "image-portrait");
    }

    function hideAllImages() {
        imageEls.forEach((img) => {
            img.classList.remove("visible");
            img.classList.add("hidden");
        });
        activeImageIndex = -1;
    }

    function hideAllBackdrops() {
        backdropEls.forEach((el) => {
            el.classList.remove("visible");
            el.classList.add("hidden");
            el.style.backgroundImage = "none";
        });
        activeBackdropIndex = -1;
    }

    function hideVideo() {
        videoEl.onended = null;
        videoEl.pause();
        videoEl.classList.remove("visible");
        videoEl.classList.add("hidden");
        videoEl.removeAttribute("src");
        videoEl.load();
    }

    function activateInLayers(elements, targetEl, updateIndex) {
        elements.forEach((el, index) => {
            const isTarget = el === targetEl;
            el.classList.toggle("visible", isTarget);
            el.classList.toggle("hidden", !isTarget);
            if (isTarget) {
                updateIndex(index);
            }
        });
    }

    function getNextLayer(elements, activeIndex) {
        if (!elements.length) {
            return null;
        }
        if (elements.length === 1 || activeIndex < 0) {
            return elements[0];
        }
        return elements[activeIndex === 0 ? 1 : 0];
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

    function decodeIntoElement(el, url) {
        el.src = url;
        if (typeof el.decode === "function") {
            return el.decode().catch(() => {});
        }
        return Promise.resolve();
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

    function chooseImageMode(width, height) {
        // Portrait detection is strict and simple (iPhone-style vertical photos).
        if (!width || !height || height > width) {
            return "image-portrait";
        }
        // Landscape images should fill the screen.
        return "image-landscape-cover";
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

        try {
            const probe = await preloadImage(url);
            if (requestId !== imageRequestToken) {
                return false;
            }

            const nextImageEl = getNextLayer(imageEls, activeImageIndex);
            const nextBackdropEl = getNextLayer(backdropEls, activeBackdropIndex);
            if (!nextImageEl || !nextBackdropEl) {
                return false;
            }

            nextBackdropEl.style.backgroundImage = `url("${backdropUrl}")`;
            activateInLayers(backdropEls, nextBackdropEl, (idx) => {
                activeBackdropIndex = idx;
            });

            await decodeIntoElement(nextImageEl, url);
            if (requestId !== imageRequestToken) {
                return false;
            }

            const modeClass = chooseImageMode(probe.naturalWidth, probe.naturalHeight);
            clearImageModeClasses();
            root.classList.add(modeClass);

            activateInLayers(imageEls, nextImageEl, (idx) => {
                activeImageIndex = idx;
            });

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

        hideAllImages();
        hideAllBackdrops();

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
                playlistKey = null;
                imageRequestToken += 1;
                clearNextTimer();
                root.classList.remove("showing-image", "showing-video");
                clearImageModeClasses();
                hideAllImages();
                hideAllBackdrops();
                hideVideo();
                setOverlay("No active album selected");
                return;
            }

            const payload = await fetchJson(`/api/albums/${status.active_album_id}/playlist`);
            const nextKey = buildPlaylistKey(status.active_album_id, payload);
            if (nextKey === playlistKey && playlist.length) {
                return;
            }

            playlist = maybeShuffle(payload.items || [], Boolean(payload.settings && payload.settings.shuffle));
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
