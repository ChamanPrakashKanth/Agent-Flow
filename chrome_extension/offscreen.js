// Local News Agent - Permanent Offscreen WebSocket Bridge
const WS_URL = "ws://127.0.0.1:8765";
let socket = null;
let reconnectTimer = null;

function connectWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      console.log("[NewsAgent Offscreen Bridge] Permanently connected to local relay on port 8765");
      if (reconnectTimer) {
        clearInterval(reconnectTimer);
        reconnectTimer = null;
      }
      socket.send(JSON.stringify({ type: "REGISTER_EXTENSION", protocol: 5 }));
    };

    socket.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log("[NewsAgent Offscreen Bridge] Received message:", message);
        if (message.type === "COMMAND") {
          // Forward command to background service worker for tab execution
          chrome.runtime.sendMessage({ type: "EXECUTE_COMMAND", data: message }, (response) => {
            if (chrome.runtime.lastError) {
              console.warn("[NewsAgent Offscreen Bridge] Runtime message error:", chrome.runtime.lastError.message);
              sendResponse({ id: message.id, type: "RESPONSE", success: false, error: chrome.runtime.lastError.message });
              return;
            }
            if (response) {
              sendResponse(response);
            }
          });
        }
      } catch (err) {
        console.error("[NewsAgent Offscreen Bridge] Error parsing message:", err);
      }
    };

    socket.onclose = () => {
      console.log("[NewsAgent Offscreen Bridge] Disconnected from relay. Auto-reconnecting in 2s...");
      scheduleReconnect();
    };

    socket.onerror = (err) => {
      console.warn("[NewsAgent Offscreen Bridge] WebSocket error:", err);
      try { socket.close(); } catch(e) {}
    };
  } catch (e) {
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (!reconnectTimer) {
    reconnectTimer = setInterval(connectWebSocket, 2000);
  }
}

function sendResponse(data) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(data));
  }
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((msg, sender, sendResp) => {
  if (msg.type === "SEND_WS_RESPONSE") {
    sendResponse(msg.data);
    sendResp({ ok: true });
  } else if (msg.type === "CHECK_WS_STATUS") {
    sendResp({ isConnected: socket && socket.readyState === WebSocket.OPEN });
  }
  return true;
});

// Start permanent connection immediately
connectWebSocket();
// Continuous heartbeat
setInterval(connectWebSocket, 5000);
