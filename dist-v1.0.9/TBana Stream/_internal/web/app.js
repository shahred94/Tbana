const alertBox = document.getElementById("alert");
const spinWidget = document.getElementById("spin-widget");
const spinWheel = document.getElementById("spin-wheel");
const spinUser = document.getElementById("spin-user");
const spinResult = document.getElementById("spin-result");
const spinResultRarity = document.getElementById("spin-result-rarity");
const spinViewerAvatar = document.getElementById(
    "spin-viewer-avatar"
);
const spinViewerFallback = document.getElementById(
    "spin-viewer-fallback"
);
const spinNotice = document.getElementById("spin-notice");
const spinNoticeMessage = document.getElementById(
    "spin-notice-message"
);
const spinOnlyOverlay =
    document.body.classList.contains(
        "spin-only-overlay"
    );
const spinSound = new Audio("/sounds/spin.mp3");

spinSound.preload = "auto";
spinSound.loop = true;
spinSound.volume = 0.65;

let spinHideTimer = null;
let spinRotation = 0;
let spinNoticeHideTimer = null;
let spinNoticeCountdownTimer = null;
let spinResultCycleTimer = null;
let spinWinnerTimer = null;
let spinSoundStopTimer = null;

const spinRarityLabels = {
    common: "Common",
    rare: "Rare",
    epic: "Epic"
};


function normalizeSpinRarity(rarity) {

    const value = String(rarity || "common").trim().toLowerCase();

    return Object.prototype.hasOwnProperty.call(
        spinRarityLabels,
        value
    )
        ? value
        : "common";
}


function applySpinResultRarity(rarity, visible = false) {

    if (!spinResultRarity) {

        return;
    }

    const normalized = normalizeSpinRarity(rarity);

    spinResultRarity.classList.remove(
        "rarity-common",
        "rarity-rare",
        "rarity-epic"
    );
    spinResultRarity.classList.add(
        `rarity-${normalized}`
    );
    spinWidget?.classList.remove(
        "rarity-common",
        "rarity-rare",
        "rarity-epic"
    );
    spinWidget?.classList.add(
        `rarity-${normalized}`
    );
    spinResultRarity.classList.toggle(
        "hidden",
        !visible
    );
    spinResultRarity.classList.remove(
        "reveal"
    );
    spinResultRarity.textContent =
        `${spinRarityLabels[normalized]} WIN`;

    if (visible) {

        requestAnimationFrame(() => {

            spinResultRarity.classList.add(
                "reveal"
            );

        });
    }
}


function spinChanceWeights(segments, chances) {

    const weights = segments.map((_, index) => {

        const value = Number(chances?.[index]);

        return Number.isFinite(value) && value >= 0
            ? value
            : 1;
    });

    if (!weights.some((weight) => weight > 0)) {

        return segments.map(() => 1);
    }

    return weights;
}


function renderSpinLabels(segments, weights) {

    spinWheel
        .querySelectorAll(".spin-segment-label")
        .forEach((label) => label.remove());

    const labelRadius = segments.length > 10 ? 108 : 104;
    const fontSize = segments.length > 10 ? 10 : 12;
    const sliceSize = 360 / Math.max(1, segments.length);

    segments.forEach((segment, index) => {

        const label = document.createElement("span");
        const angle =
            index * sliceSize +
            sliceSize / 2;

        if (weights[index] <= 0) {

            return;
        }

        label.className = "spin-segment-label";
        label.innerText = segment;
        label.style.fontSize = `${fontSize}px`;
        label.style.transform =
            "translate(-50%, -50%) " +
            `rotate(${angle}deg) ` +
            `translateY(-${labelRadius}px) ` +
            "rotate(90deg)";

        spinWheel.appendChild(label);
    });
}


function showAlert(user, gift) {

    const userElement =
        document.getElementById("user");

    const giftNameElement =
        document.getElementById("gift-name");

    if (!alertBox || !userElement || !giftNameElement) {

        return;

    }

    userElement.innerText = user;
    giftNameElement.innerText = gift;

    alertBox.classList.remove("hidden");
    alertBox.classList.add("show");


    setTimeout(() => {

        alertBox.classList.remove("show");
        alertBox.classList.add("hidden");

    }, 5000);
}


function viewerInitials(name) {

    const trimmed = String(
        name || "Viewer"
    )
    .trim()
    .replace(
        /\s+/g,
        " "
    );

    const parts = trimmed.split(" ");
    const initials = parts
        .slice(0, 2)
        .map((part) => part[0] || "")
        .join("")
        .trim();

    return (initials || trimmed[0] || "V")
        .toUpperCase()
        .slice(0, 2);
}


function applySpinViewerAvatar(data) {

    if (!spinViewerAvatar || !spinViewerFallback) {

        return;
    }

    const viewerName = data.user || "Viewer";
    const avatarUrl =
        data.viewer_avatar_url ||
        data.avatar_url ||
        data.profile_picture_url ||
        "";

    spinViewerFallback.innerText =
        viewerInitials(viewerName);

    spinViewerAvatar.alt =
        `${viewerName} avatar`;

    spinViewerAvatar.onerror = () => {

        spinViewerAvatar.classList.add("hidden");
        spinViewerFallback.classList.remove("hidden");
    };

    if (avatarUrl) {

        spinViewerAvatar.src = avatarUrl;
        spinViewerAvatar.classList.remove("hidden");
        spinViewerFallback.classList.add("hidden");
        return;
    }

    spinViewerAvatar.removeAttribute("src");
    spinViewerAvatar.classList.add("hidden");
    spinViewerFallback.classList.remove("hidden");
}


function playSpinSound(durationMs) {

    try {

        clearTimeout(spinSoundStopTimer);
        spinSound.pause();
        spinSound.currentTime = 0;

        const playResult = spinSound.play();

        if (
            playResult
            &&
            typeof playResult.catch === "function"
        ) {

            playResult.catch((error) => {

                console.warn(
                    "Unable to play spin sound:",
                    error
                );

                });
        }

        if (
            Number.isFinite(durationMs)
            &&
            durationMs > 0
        ) {

            spinSoundStopTimer = setTimeout(
                () => {

                    spinSound.pause();
                    spinSound.currentTime = 0;

                },
                durationMs
            );
        }

    } catch (error) {

        console.warn(
            "Unable to play spin sound:",
            error
        );

    }
}


function rarityColorPalette(rarity, index) {

    const palettes = {
        common: ["#22c55e", "#34d399", "#14b8a6"],
        rare: ["#8b5cf6", "#a855f7", "#c084fc"],
        epic: ["#f59e0b", "#eab308", "#f97316"]
    };

    const normalized = normalizeSpinRarity(rarity);
    const colors = palettes[normalized] || palettes.common;

    return colors[index % colors.length];
}


function wheelGradient(segments, weights, rarities = []) {

    const sliceSize = 100 / Math.max(1, segments.length);

    const stops = segments.map((_, index) => {

        const rarity = normalizeSpinRarity(
            rarities?.[index]
        );

        const start = (index * sliceSize).toFixed(2);
        const end = ((index + 1) * sliceSize).toFixed(2);

        return `${rarityColorPalette(rarity, index)} ${start}% ${end}%`;
    });

    return `conic-gradient(${stops.join(", ")})`;
}


function showSpinWidget(data) {

    if (!spinWidget || !spinWheel || !spinUser || !spinResult) {

        return;

    }

    const segments =
        Array.isArray(data.segments) && data.segments.length
            ? data.segments
            : [
                "Try Again",
                "Shoutout",
                "Bonus Sound",
                "Lucky Star",
                "Dance",
                "Mega Hype",
                "Mystery",
                "Jackpot"
            ];

    const result =
        data.result || segments[
            Math.floor(
                Math.random() * segments.length
            )
        ];

    const requestedWinnerIndex =
        Number(data.winner_index);
    const winnerIndex =
        Number.isInteger(requestedWinnerIndex)
        &&
        requestedWinnerIndex >= 0
        &&
        requestedWinnerIndex < segments.length
            ? requestedWinnerIndex
            : Math.max(
                0,
                segments.indexOf(result)
            );

    const weights =
        spinChanceWeights(
            segments,
            data.chances
        );
    const rarities =
        Array.isArray(data.rarities) && data.rarities.length
            ? data.rarities
            : segments.map(() => "common");

    const spinMs =
        Number(data.spin_ms) || 5200;

    const targetCenter =
        (winnerIndex + 0.5) *
        (360 / Math.max(1, segments.length));

    const finalRotation =
        spinRotation +
        360 * 7 +
        (360 - targetCenter);

    spinRotation = finalRotation;

    spinUser.innerText =
        data.user || "Viewer";
    applySpinViewerAvatar(data);
    applySpinResultRarity(data.winner_rarity, false);
    playSpinSound(spinMs);

    clearInterval(spinResultCycleTimer);
    clearTimeout(spinWinnerTimer);

    let displayedSegment = Math.floor(
        Math.random() * segments.length
    );

    spinResult.innerText =
        segments[displayedSegment];

    spinWheel.style.background =
        wheelGradient(
            segments,
            weights,
            rarities
        );

    renderSpinLabels(
        segments,
        weights
    );

    spinWheel.style.transition =
        "none";

    spinWheel.style.transform =
        `rotate(${finalRotation - 360 * 7}deg)`;

    spinWidget.classList.remove("hidden");
    spinWidget.classList.add("show");

    clearTimeout(spinHideTimer);

    requestAnimationFrame(() => {

        requestAnimationFrame(() => {

            spinWheel.style.transition =
                `transform ${spinMs}ms cubic-bezier(0.12, 0.72, 0.12, 1)`;

            spinWheel.style.transform =
                `rotate(${finalRotation}deg)`;
        });
    });

    spinResultCycleTimer = setInterval(() => {

        displayedSegment =
            (displayedSegment + 1) % segments.length;
        spinResult.innerText =
            segments[displayedSegment];

    }, 140);

    spinWinnerTimer = setTimeout(() => {

        clearInterval(spinResultCycleTimer);
        spinResult.innerText =
            result;
        applySpinResultRarity(data.winner_rarity, true);

        spinWidget.classList.add("winner");

    }, spinMs);

    const resultHoldMs =
        Number(data.result_hold_ms) || 3000;

    spinHideTimer = setTimeout(() => {

        spinWidget.classList.remove("show");
        spinWidget.classList.remove("winner");
        spinWidget.classList.remove(
            "rarity-common",
            "rarity-rare",
            "rarity-epic"
        );
        spinWidget.classList.add("hidden");

    }, spinMs + resultHoldMs);
}


function formatSpinCooldown(totalSeconds) {

    const safeSeconds = Math.max(
        1,
        Math.ceil(totalSeconds)
    );
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const seconds = safeSeconds % 60;

    if (hours) {

        return `${hours}h ${String(minutes).padStart(2, "0")}m ` +
            `${String(seconds).padStart(2, "0")}s`;
    }

    if (minutes) {

        return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
    }

    return `${seconds}s`;
}


function showSpinNotice(data) {

    if (!spinNotice || !spinNoticeMessage) {

        return;
    }

    clearTimeout(spinNoticeHideTimer);
    clearInterval(spinNoticeCountdownTimer);

    let remainingSeconds =
        Math.max(0, Number(data.remaining_seconds) || 0);
    const user = data.user || "Guest";
    const status = data.viewer_status || "Viewer";

    const render = () => {

        spinNoticeMessage.innerText = remainingSeconds > 0
            ? `@${user} • ${status} • cooldown remaining: ` +
                formatSpinCooldown(remainingSeconds)
            : (
                data.message ||
                `@${user} • ${status} • !spin is unavailable.`
            );
    };

    render();
    spinNotice.classList.remove("hidden");
    spinNotice.classList.add("show");

    if (remainingSeconds > 0) {

        spinNoticeCountdownTimer = setInterval(() => {

            remainingSeconds = Math.max(0, remainingSeconds - 1);
            render();

            if (remainingSeconds <= 0) {

                clearInterval(spinNoticeCountdownTimer);
            }

        }, 1000);
    }

    spinNoticeHideTimer = setTimeout(() => {

        clearInterval(spinNoticeCountdownTimer);
        spinNotice.classList.remove("show");
        spinNotice.classList.add("hidden");

    }, 8000);
}


let socket = null;
let pingTimer = null;


function connectWebSocket() {

    const protocol =
        window.location.protocol === "https:"
            ? "wss:"
            : "ws:";

    const screen =
        new URLSearchParams(
            window.location.search
        ).get("screen") || "1";

    socket = new WebSocket(
        (
            `${protocol}//${window.location.host}/ws/events`
            +
            `?screen=${encodeURIComponent(screen)}`
            +
            `&overlay=${spinOnlyOverlay ? "spin" : "screen"}`
        )
    );


    socket.onopen = () => {

        console.log(
            "Connected to TBana Stream"
        );


        pingTimer = setInterval(() => {

            if (
                socket.readyState === WebSocket.OPEN
            ) {

                socket.send("ping");

            }

        }, 10000);
    };


    socket.onmessage = (event) => {

        const message = JSON.parse(
            event.data
        );


        console.log(
            "Received:",
            message
        );


        if (
            message.type === "overlay"
            &&
            message.name === "gift"
        ) {

            showAlert(
                message.data.user,
                message.data.gift
            );
        }

        if (
            spinOnlyOverlay
            &&
            message.type === "spin"
        ) {

            showSpinWidget(
                message.data || {}
            );
        }

        if (
            spinOnlyOverlay
            &&
            message.type === "spin_notice"
        ) {

            showSpinNotice(
                message.data || {}
            );
        }
    };


    socket.onclose = () => {

        console.log(
            "Disconnected from TBana Stream"
        );


        if (pingTimer) {

            clearInterval(
                pingTimer
            );

            pingTimer = null;
        }


        console.log(
            "Reconnecting in 3 seconds..."
        );


        setTimeout(
            connectWebSocket,
            3000
        );
    };


    socket.onerror = (error) => {

        console.log(
            "WebSocket error:",
            error
        );

    };
}


// Start connection
connectWebSocket();
