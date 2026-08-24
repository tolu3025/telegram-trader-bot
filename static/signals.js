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

const triggerGrid = document.getElementById('triggerGrid');
const briefingContainer = document.getElementById('briefingContainer');
const activeBriefingSession = document.getElementById('activeBriefingSession');
const emptyBriefingState = document.getElementById('emptyBriefingState');
const briefingMarkdown = document.getElementById('briefingMarkdown');

const signalAlertCard = document.getElementById('signalAlertCard');
const signalDirBadge = document.getElementById('signalDirBadge');
const signalCardBody = document.getElementById('signalCardBody');
const executeSignalBtn = document.getElementById('executeSignalBtn');

let currentMode = 'forex';
let activeSignalData = null;

// Init
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    setInterval(fetchStatus, 10000);

    // Trigger Grid Click events
    const triggerButtons = triggerGrid.querySelectorAll('button');
    triggerButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const sessionKey = btn.getAttribute('data-session');
            runSessionScan(sessionKey, btn);
        });
    });

    // Execute signal handler
    executeSignalBtn.addEventListener('click', () => {
        if (activeSignalData) {
            const sig = activeSignalData;
            const params = new URLSearchParams({
                symbol: sig.symbol,
                direction: sig.direction,
                entry: sig.entry,
                sl: sig.sl,
                tp: sig.tp,
                thesis: sig.thesis || 'Manual session signal'
            });
            window.location.href = `/?${params.toString()}`;
        }
    });
});

// Fetch general status
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

// Trigger Session Scan
async function runSessionScan(sessionKey, buttonEl) {
    // Disable all buttons in grid
    const triggerButtons = triggerGrid.querySelectorAll('button');
    triggerButtons.forEach(b => b.disabled = true);
    
    const originalText = buttonEl.innerText;
    buttonEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Scanning...';
    
    // Hide previous signal card
    signalAlertCard.style.display = 'none';
    briefingMarkdown.innerHTML = '';
    emptyBriefingState.style.display = 'none';
    activeBriefingSession.style.display = 'none';

    // Show loading state in briefing output container
    briefingMarkdown.innerHTML = `
        <div class="no-data" style="padding: 40px 0;">
            <i class="fa-solid fa-binoculars fa-spin" style="font-size: 2.5rem; color: var(--neon-cyan); margin-bottom: 10px; display: block;"></i>
            Marcus Vance is scanning live order books and detecting structure confluences. Please stand by...
        </div>
    `;

    try {
        const res = await fetch(`/api/signals/trigger?session=${sessionKey}`, {
            method: 'POST'
        });
        const data = await res.json();

        // Clear loading state
        briefingMarkdown.innerHTML = '';

        if (res.ok) {
            // Update session badge
            activeBriefingSession.innerText = data.session_name.toUpperCase();
            activeBriefingSession.style.display = 'inline-block';

            // Parse Briefing Markdown using marked.js
            let parsedHtml = data.analysis || 'No analysis generated.';
            if (typeof window.marked !== 'undefined' && window.marked.parse) {
                parsedHtml = window.marked.parse(parsedHtml);
            } else if (typeof marked !== 'undefined' && marked.parse) {
                parsedHtml = marked.parse(parsedHtml);
            } else {
                parsedHtml = parsedHtml.replace(/\n/g, '<br>');
            }
            briefingMarkdown.innerHTML = parsedHtml;

            // Load and display Signal card if available
            if (data.has_signal && data.signal) {
                activeSignalData = data.signal;
                const sig = data.signal;
                
                signalDirBadge.innerText = sig.direction;
                signalDirBadge.style.background = sig.direction === 'LONG' ? 'var(--neon-green)' : 'var(--neon-red)';
                
                signalCardBody.innerHTML = `
                    <div style="margin-bottom: 4px;">Asset: <strong style="color: var(--neon-cyan);">${sig.symbol}</strong></div>
                    <div style="margin-bottom: 4px;">Entry Level: <strong>${sig.entry}</strong></div>
                    <div style="margin-bottom: 4px;">Stop Loss: <strong style="color: var(--neon-red);">${sig.sl}</strong></div>
                    <div style="margin-bottom: 4px;">Take Profit: <strong style="color: var(--neon-green);">${sig.tp}</strong></div>
                    <div style="margin-top: 6px; font-style: italic; color: var(--text-muted); font-size: 11px;">Thesis: "${sig.thesis}"</div>
                `;
                
                signalAlertCard.style.display = 'block';
            } else {
                activeSignalData = null;
                signalAlertCard.style.display = 'none';
            }

        } else {
            briefingMarkdown.innerHTML = `<div style="color: var(--neon-red); text-align: center; padding: 20px 0;">Error scanning session: ${data.detail || 'Unknown error'}</div>`;
        }

    } catch (e) {
        console.error('Trigger signals error:', e);
        briefingMarkdown.innerHTML = '<div style="color: var(--neon-red); text-align: center; padding: 20px 0;">Network error. Could not reach server.</div>';
    } finally {
        // Re-enable grid buttons
        triggerButtons.forEach(b => b.disabled = false);
        buttonEl.innerText = originalText;
    }
}
