(function () {
    const body = document.body;
    const statusUrl = body.dataset.statusUrl;
    const root = document.getElementById("player-root");
    const backdropEl = document.getElementById("player-backdrop");
    const overlay = document.getElementById("player-overlay");
    const imgEl = document.getElementById("player-image");
    const videoEl = document.getElementById("player-video");

    let playlist = [];
    let currentIndex = 0;
    let timer = null;
    let activeAlbumId = null;
    let playlistKey = null;

    function setOverlay(text) {
        overlay.textContent = text;
    }

    function setImageOrientationClass() {
        const naturalWidth = Number(imgEl.naturalWidth || 0);
        const naturalHeight = Number(imgEl.naturalHeight || 0);
        const isLandscape = naturalWidth > 0 && naturalHeight > 0
            ? naturalWidth >= naturalHeight
            : false;
        root.classList.add("showing-image");
        root.classList.remove("showing-video");
        root.classList.toggle("image-landscape", isLandscape);
        root.classList.toggle("image-portrait", !isLandscape);
    }

    function showImage(item) {
        const url = item.normalized_url;
        const backdropUrl = item.thumb_url || url;

        videoEl.pause();
        videoEl.classList.add("hidden");
        videoEl.removeAttribute("src");
        videoEl.load();

        root.classList.add("showing-image");
        root.classList.remove("showing-video", "image-landscape", "image-portrait");

        if (backdropEl) {
            backdropEl.style.backgroundImage = `url("${backdropUrl}")`;
        }

        imgEl.onload = () => setImageOrientationClass();
        imgEl.src = url;
        imgEl.classList.remove("hidden");
    }

    function showVideo(url) {
        root.classList.add("showing-video");
        root.classList.remove("showing-image", "image-landscape", "image-portrait");
        if (backdropEl) {
            backdropEl.style.backgroundImage = "none";
        }

        imgEl.classList.add("hidden");

        videoEl.src = url;
        videoEl.classList.remove("hidden");
        videoEl.play().catch(() => {
            setOverlay("Video autoplay blocked; tap to continue");
        });
    }

    function scheduleNext(ms) {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(playNext, ms);
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
            videoEl.onended = () => playNext();
            return;
        }

        setOverlay("");
        showImage(item);
        const durationMs = Math.max(1, Number(item.duration_seconds || 8)) * 1000;
        scheduleNext(durationMs);
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
                root.classList.remove("showing-image", "showing-video", "image-landscape", "image-portrait");
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

            const items = payload.items || [];
            playlist = maybeShuffle(items, Boolean(payload.settings && payload.settings.shuffle));
            activeAlbumId = status.active_album_id;
            playlistKey = nextKey;
            currentIndex = 0;

            if (!playlist.length) {
                setOverlay("Active album has no ready media");
                return;
            }

            playNext();
        } catch (err) {
            setOverlay("Player failed to load playlist");
        }
    }

    refreshPlaylist();
    setInterval(refreshPlaylist, 5000);
})();
