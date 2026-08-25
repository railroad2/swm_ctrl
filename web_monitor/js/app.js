(function () {
    const config = window.SWM_RUNTIME_CONFIG;

    const matrixRoot = document.getElementById("matrix-root");
    const wsState = document.getElementById("ws-state");
    const wsUri = document.getElementById("ws-uri");
    const eventState = document.getElementById("event-state");
    const activeCount = document.getElementById("active-count");
    const activeList = document.getElementById("active-list");
    const refreshBtn = document.getElementById("refresh-btn");
    const measurementStatus = document.getElementById("measurement-status");
    const measurementType = document.getElementById("measurement-type");
    const measurementTarget = document.getElementById("measurement-target");
    const measurementProgressText = document.getElementById("measurement-progress-text");
    const measurementProgressBar = document.getElementById("measurement-progress-bar");

    wsUri.textContent = config.wsUrl;

    function setGatewayState(text, isConnected) {
        wsState.textContent = text;
        wsState.classList.toggle("connected", isConnected);
        wsState.classList.toggle("disconnected", !isConnected);
    }

    function extractPinsFromMessage(msg) {
        if (!msg || typeof msg !== "object") {
            return null;
        }

        if (
            (msg.event === "pinstat_snapshot" ||
             msg.event === "pinstat_update" ||
             msg.event === "get") &&
            msg.data &&
            Array.isArray(msg.data.pins)
        ) {
            return msg.data.pins;
        }

        if (
            msg.ok === 1 &&
            msg.cmd === "PINSTAT" &&
            msg.which === "ALL" &&
            Array.isArray(msg.pins)
        ) {
            return msg.pins;
        }

        return null;
    }

    function targetLabel(mode, target) {
        if (!Number.isInteger(target)) {
            return "-";
        }
        if (mode === "channel") {
            const row = String.fromCharCode("A".charCodeAt(0) + Math.floor(target / 16));
            const col = String(target % 16).padStart(2, "0");
            return `Channel ${target} (${row}${col})`;
        }
        if (mode === "row") {
            return `Row ${String.fromCharCode("A".charCodeAt(0) + target)}`;
        }
        if (mode === "column") {
            return `Column ${String(target).padStart(2, "0")}`;
        }
        return "-";
    }

    function renderMeasurement(measurement) {
        if (!measurement || typeof measurement !== "object") {
            return;
        }

        const status = String(measurement.status || "idle");
        const modeNames = {
            channel: "Individual pixels",
            row: "Row-wise",
            column: "Column-wise",
        };
        const completed = Number.isInteger(measurement.completed) ? measurement.completed : 0;
        const total = Number.isInteger(measurement.total) ? measurement.total : 0;
        const percent = total > 0 ? Math.max(0, Math.min(100, completed / total * 100)) : 0;

        measurementStatus.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        measurementStatus.classList.remove(
            "measurement-idle",
            "measurement-active",
            "measurement-completed",
            "measurement-failed",
        );
        if (status === "failed") {
            measurementStatus.classList.add("measurement-failed");
        } else if (status === "completed") {
            measurementStatus.classList.add("measurement-completed");
        } else if (status === "stopped") {
            measurementStatus.classList.add("measurement-idle");
        } else {
            measurementStatus.classList.add("measurement-active");
        }

        measurementType.textContent = `${measurement.kind || "-"} · ${modeNames[measurement.mode] || "-"}`;
        measurementTarget.textContent = targetLabel(measurement.mode, measurement.target);
        measurementProgressText.textContent = `${completed} / ${total}`;
        measurementProgressBar.style.width = `${percent}%`;
    }

    const matrixView = new window.MatrixView(matrixRoot, {
        matrixSize: config.matrixSize,
    });

    matrixView.build();

    const gateway = new window.GatewayClient({
        wsUrl: config.wsUrl,
        reconnectMs: config.reconnectMs,
    });

    gateway.onOpen = () => {
        setGatewayState("Connected", true);
    };

    gateway.onClose = () => {
        setGatewayState("Disconnected", false);
    };

    gateway.onError = (error) => {
        console.error("WebSocket error:", error);
        setGatewayState("Error", false);
    };

    gateway.onEvent = (msg) => {
        if (typeof msg.event === "string") {
            eventState.textContent = msg.event;
        }

        const pins = extractPinsFromMessage(msg);

        if (msg.measurement) {
            renderMeasurement(msg.measurement);
        }

        if (pins) {
            const activePins = matrixView.renderPins(pins);
            const labels = matrixView.activePinsToLabels(activePins);

            activeCount.textContent = String(activePins.length);
            activeList.textContent = labels.length > 0 ? labels.join(" ") : "(none)";
        }
    };

    refreshBtn.addEventListener("click", () => {
        gateway.requestRefresh();
    });

    gateway.connect();
})();
