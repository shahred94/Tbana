const alertBox = document.getElementById("alert");
const spinWidget = document.getElementById("spin-widget");
const spinWheel = document.getElementById("spin-wheel");
const spinUser = document.getElementById("spin-user");
const spinResult = document.getElementById("spin-result");

let spinHideTimer = null;
let spinRotation = 0;


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


function wheelGradient(segments) {

    const colors = [
        "#22c55e",
        "#06b6d4",
        "#a855f7",
        "#f97316",
        "#eab308",
        "#ef4444",
        "#14b8a6",
        "#ec4899"
    ];

    const slice = 100 / segments.length;

    const stops = segments.map((_, index) => {

        const start = (slice * index).toFixed(2);
        const end = (slice * (index + 1)).toFixed(2);

        return `${colors[index % colors.length]} ${start}% ${end}%`;
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

    const winnerIndex = Math.max(
        0,
        segments.indexOf(result)
    );

    const spinMs =
        Number(data.spin_ms) || 5200;

    const sliceDegrees =
        360 / segments.length;

    const targetCenter =
        winnerIndex * sliceDegrees + sliceDegrees / 2;

    const finalRotation =
        spinRotation +
        360 * 7 +
        (360 - targetCenter);

    spinRotation = finalRotation;

    spinUser.innerText =
        data.user || "Viewer";

    spinResult.innerText =
        "Spinning...";

    spinWheel.style.background =
        wheelGradient(segments);

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

    setTimeout(() => {

        spinResult.innerText =
            result;

        spinWidget.classList.add("winner");

    }, spinMs);

    spinHideTimer = setTimeout(() => {

        spinWidget.classList.remove("show");
        spinWidget.classList.remove("winner");
        spinWidget.classList.add("hidden");

    }, spinMs + 5000);
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
        `${protocol}//${window.location.host}/ws/events?screen=${screen}`
    );


    socket.onopen = () => {

        console.log(
            "Connected to LiveTrigger"
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

        if (message.type === "spin") {

            showSpinWidget(
                message.data || {}
            );
        }
    };


    socket.onclose = () => {

        console.log(
            "Disconnected from LiveTrigger"
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
