// Initialize Telegram WebApp
const webApp = window.Telegram?.WebApp;
if (webApp) {
    webApp.ready();
    webApp.expand();
}

// DOM Elements
const statusIndicator = document.getElementById('statusIndicator');
const statusText = document.getElementById('statusText');
const modeBadge = document.getElementById('modeBadge');
const exchangeBadge = document.getElementById('exchangeBadge');

const chatMessages = document.getElementById('chatMessages');
const marcusInput = document.getElementById('marcusInput');
const marcusSendBtn = document.getElementById('marcusSendBtn');

let currentMode = 'forex';

// Init
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    setInterval(fetchStatus, 10000);

    // Marcus Chat Events
    marcusSendBtn.addEventListener('click', handleMarcusSend);
    marcusInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleMarcusSend();
        }
    });

    // Quick Prompt Clicks
    document.querySelectorAll('.quick-prompt-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const promptText = btn.getAttribute('data-prompt');
            marcusInput.value = promptText;
            handleMarcusSend();
        });
    });
});

// Fetch general server & exchange status
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        currentMode = data.mode;
        
        // Update header UI
        statusIndicator.className = 'status-indicator connected';
        statusText.innerText = data.live_execution ? 'LIVE API CONNECTED' : 'SIMULATOR MODE';
        
        modeBadge.innerText = `MODE: ${data.mode}`;
        exchangeBadge.innerText = `${data.exchange}: ${data.exchange_mode}`;
        
    } catch (e) {
        console.error('Failed to sync status:', e);
        statusIndicator.className = 'status-indicator error';
        statusText.innerText = 'OFFLINE';
    }
}

// Post Chat Message
async function handleMarcusSend() {
    const text = marcusInput.value.trim();
    if (!text) return;

    // Clear input & disable controls
    marcusInput.value = '';
    marcusInput.disabled = true;
    marcusSendBtn.disabled = true;

    // Append user message
    const userMsgDiv = document.createElement('div');
    userMsgDiv.className = 'chat-msg user';
    userMsgDiv.innerHTML = `<div class="chat-bubble user-bubble">${text}</div>`;
    chatMessages.appendChild(userMsgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Append typing indicator
    const typingIndicator = document.createElement('div');
    typingIndicator.className = 'chat-msg ai';
    typingIndicator.id = 'typingIndicator';
    typingIndicator.innerHTML = `
        <div class="chat-bubble typing-bubble">
            Marcus is analyzing<span class="typing-dots"><span>.</span><span>.</span><span>.</span></span>
        </div>
    `;
    chatMessages.appendChild(typingIndicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        const data = await res.json();

        // Remove typing indicator
        const indicator = document.getElementById('typingIndicator');
        if (indicator) indicator.remove();

        // Append AI response
        const aiMsgDiv = document.createElement('div');
        aiMsgDiv.className = 'chat-msg ai';
        
        let parsedReply = data.reply || 'No response.';
        if (typeof window.marked !== 'undefined' && window.marked.parse) {
            parsedReply = window.marked.parse(parsedReply);
        } else if (typeof marked !== 'undefined' && marked.parse) {
            parsedReply = marked.parse(parsedReply);
        } else {
            parsedReply = parsedReply
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/`(.*?)`/g, '<code>$1</code>')
                .replace(/\n/g, '<br>');
        }
        
        aiMsgDiv.innerHTML = `
            <div class="chat-bubble ai-bubble">
                <strong>Marcus Vance:</strong>
                <div class="markdown-content">${parsedReply}</div>
            </div>
        `;
        chatMessages.appendChild(aiMsgDiv);

        // If Marcus generated an actionable signal, display an interactive trade setup card
        if (data.has_signal && data.signal) {
            const sig = data.signal;
            const signalCardDiv = document.createElement('div');
            signalCardDiv.className = 'chat-msg ai';
            signalCardDiv.innerHTML = `
                <div class="chat-bubble ai-bubble signal-chat-card glass" style="margin-top: 8px; width: 100%; border: 1px solid var(--neon-cyan); background: rgba(0, 242, 254, 0.03);">
                    <div style="font-weight: 700; color: var(--neon-cyan); margin-bottom: 8px; font-size: 13px; display: flex; justify-content: space-between;">
                        <span>🎯 ACTIONABLE SIGNAL</span>
                        <span style="background: ${sig.direction === 'LONG' ? 'var(--neon-green)' : 'var(--neon-red)'}; color: #000; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 800;">${sig.direction}</span>
                    </div>
                    <div style="font-size: 12px; line-height: 1.5; color: var(--text-primary); margin-bottom: 12px;">
                        <div style="margin-bottom: 4px;">Asset: <strong style="color: var(--neon-cyan);">${sig.symbol}</strong></div>
                        <div style="margin-bottom: 4px;">Entry Level: <strong>${sig.entry}</strong></div>
                        <div style="margin-bottom: 4px;">Stop Loss: <strong style="color: var(--neon-red);">${sig.sl}</strong></div>
                        <div style="margin-bottom: 4px;">Take Profit: <strong style="color: var(--neon-green);">${sig.tp}</strong></div>
                        <div style="margin-top: 6px; font-style: italic; color: var(--text-muted); font-size: 11px;">Thesis: "${sig.thesis}"</div>
                    </div>
                    <button class="chat-confirm-btn" onclick="redirectToConsole('${sig.symbol}', '${sig.direction}', ${sig.entry}, ${sig.sl}, ${sig.tp}, '${sig.thesis}')" style="width: 100%; padding: 8px; border-radius: 8px; background: var(--grad-primary); border: none; color: #000; font-weight: 700; font-size: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 0 10px rgba(0, 242, 254, 0.25);">
                        <i class="fa-solid fa-signature"></i> Approve Setup
                    </button>
                </div>
            `;
            chatMessages.appendChild(signalCardDiv);
        }
    } catch (e) {
        console.error('Chat error:', e);
        const indicator = document.getElementById('typingIndicator');
        if (indicator) indicator.remove();

        const errorMsgDiv = document.createElement('div');
        errorMsgDiv.className = 'chat-msg ai';
        errorMsgDiv.innerHTML = `
            <div class="chat-bubble ai-bubble">
                <strong>Marcus Vance:</strong> Had some connectivity issues, kid. Try repeating that.
            </div>
        `;
        chatMessages.appendChild(errorMsgDiv);
    } finally {
        marcusInput.disabled = false;
        marcusSendBtn.disabled = false;
        marcusInput.focus();
        setTimeout(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 100);
    }
}

// Redirect utility: redirects to console index and passes parameters as URL hash
window.redirectToConsole = (symbol, direction, entry, sl, tp, thesis) => {
    const params = new URLSearchParams({
        symbol,
        direction,
        entry,
        sl,
        tp,
        thesis
    });
    window.location.href = `/?${params.toString()}`;
};
