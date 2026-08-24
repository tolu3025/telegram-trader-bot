// Initialize Telegram WebApp
const webApp = window.Telegram?.WebApp;
if (webApp) {
    webApp.ready();
    webApp.expand();
}

// State Management
let currentMode = 'crypto';
let tvWidget = null;

// DOM Elements
const statusIndicator = document.getElementById('statusIndicator');
const statusText = document.getElementById('statusText');
const modeBadge = document.getElementById('modeBadge');
const exchangeBadge = document.getElementById('exchangeBadge');
const balanceVal = document.getElementById('balanceVal');
const posCount = document.getElementById('posCount');
const tradeSymbol = document.getElementById('tradeSymbol');
const tradeForm = document.getElementById('tradeForm');
const submitBtn = document.getElementById('submitBtn');
const positionsList = document.getElementById('positionsList');
const historyList = document.getElementById('historyList');
const scanTableBody = document.getElementById('scanTableBody');
const refreshScanBtn = document.getElementById('refreshScanBtn');


// Modal Elements
const feedbackModal = document.getElementById('feedbackModal');
const modalDecisionBadge = document.getElementById('modalDecisionBadge');
const modalFeedbackText = document.getElementById('modalFeedbackText');
const modalTradeStats = document.getElementById('modalTradeStats');
const modalPosId = document.getElementById('modalPosId');
const modalSize = document.getElementById('modalSize');
const modalRisk = document.getElementById('modalRisk');
const closeModalBtn = document.getElementById('closeModalBtn');
const confirmModalBtn = document.getElementById('confirmModalBtn');

// Map yfinance symbols to TradingView symbols
const tvSymbolMap = {
    'EURUSD': 'FX:EURUSD',
    'GBPUSD': 'FX:GBPUSD',
    'USDJPY': 'FX:USDJPY',
    'AUDUSD': 'FX:AUDUSD',
    'XAUUSD': 'OANDA:XAUUSD',
    'BTC-USD': 'BINANCE:BTCUSDT',
    'ETH-USD': 'BINANCE:ETHUSDT',
    'SOL-USD': 'BINANCE:SOLUSDT',
    'BNB-USD': 'BINANCE:BNBUSDT',
    'XRP-USD': 'BINANCE:XRPUSDT',
    'DOGE-USD': 'BINANCE:DOGEUSDT'
};

// Symbol dropdown lists by mode
const symbolsByMode = {
    'forex': [
        { label: 'EUR/USD', value: 'EURUSD' },
        { label: 'GBP/USD', value: 'GBPUSD' },
        { label: 'USD/JPY', value: 'USDJPY' },
        { label: 'AUD/USD', value: 'AUDUSD' },
        { label: 'XAU/USD (Gold)', value: 'XAUUSD' }
    ],
    'crypto': [
        { label: 'BTC/USDT', value: 'BTC-USD' },
        { label: 'ETH/USDT', value: 'ETH-USD' },
        { label: 'SOL/USDT', value: 'SOL-USD' },
        { label: 'BNB/USDT', value: 'BNB-USD' },
        { label: 'XRP/USDT', value: 'XRP-USD' },
        { label: 'DOGE/USDT', value: 'DOGE-USD' }
    ],
    'perpetual': [
        { label: 'BTC/USDT (Linear Perp)', value: 'BTC-USD' },
        { label: 'ETH/USDT (Linear Perp)', value: 'ETH-USD' },
        { label: 'SOL/USDT (Linear Perp)', value: 'SOL-USD' },
        { label: 'BNB/USDT (Linear Perp)', value: 'BNB-USD' },
        { label: 'XRP/USDT (Linear Perp)', value: 'XRP-USD' },
        { label: 'DOGE/USDT (Linear Perp)', value: 'DOGE-USD' }
    ]
};

// Init application
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTradingViewWidget('BINANCE:BTCUSDT');
    fetchStatus();
    fetchPositions();
    fetchHistory();
    fetchScanData();
    
    // Periodically sync balance and positions every 10 seconds
    setInterval(fetchStatus, 10000);
    setInterval(fetchPositions, 10000);
    
    // Form submissions
    tradeForm.addEventListener('submit', handleTradeSubmit);
    
    // Close modal
    closeModalBtn.addEventListener('click', hideModal);
    confirmModalBtn.addEventListener('click', hideModal);
    
    // Refresh scan
    refreshScanBtn.addEventListener('click', fetchScanData);
    
    // Reload TV Widget on symbol select change
    tradeSymbol.addEventListener('change', (e) => {
        const tvSym = tvSymbolMap[e.target.value] || 'BINANCE:BTCUSDT';
        initTradingViewWidget(tvSym);
    });

    // Check for query parameters to prefill trade setups (redirected from chat or signals page)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('symbol') && urlParams.has('entry')) {
        const symbol = urlParams.get('symbol');
        const direction = urlParams.get('direction') || 'LONG';
        const entry = urlParams.get('entry');
        const sl = urlParams.get('sl');
        const tp = urlParams.get('tp');
        const thesis = urlParams.get('thesis') || '';

        // Switch to console/terminal tab
        const consoleTabBtn = document.querySelector('.tab-btn[data-tab="console"]');
        if (consoleTabBtn) consoleTabBtn.click();

        // Wait a tiny bit for UI update
        setTimeout(() => {
            // Select symbol
            tradeSymbol.value = symbol;
            
            // Set direction
            if (direction.toUpperCase() === 'LONG') {
                document.getElementById('dirLong').checked = true;
            } else {
                document.getElementById('dirShort').checked = true;
            }
            
            // Fill values
            document.getElementById('tradeEntry').value = entry;
            document.getElementById('tradeSl').value = sl;
            document.getElementById('tradeTp').value = tp;
            document.getElementById('tradeThesis').value = thesis;

            // Scroll to order form
            document.getElementById('tradeForm').scrollIntoView({ behavior: 'smooth' });

            // Clear URL query parameters to avoid double-filling on page reload
            window.history.replaceState({}, document.title, window.location.pathname);
        }, 300);
    }
});


// Setup navigation tabs
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            
            // Switch tabs
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(`tab-${targetTab}`).classList.add('active');
            
            // Refresh specific data
            if (targetTab === 'positions') fetchPositions();
            if (targetTab === 'history') fetchHistory();
            if (targetTab === 'scan') fetchScanData();
        });
    });
}

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
        balanceVal.innerText = Number(data.balance).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        
        // Populate Symbol drop-down dynamically if mode changes
        populateSymbolsDropdown(data.mode);
        
    } catch (e) {
        console.error('Failed to sync status:', e);
        statusIndicator.className = 'status-indicator error';
        statusText.innerText = 'OFFLINE';
    }
}

// Populate Symbol Select Form Option
function populateSymbolsDropdown(mode) {
    const selectedVal = tradeSymbol.value;
    tradeSymbol.innerHTML = '';
    
    const symbols = symbolsByMode[mode] || symbolsByMode['crypto'];
    symbols.forEach(sym => {
        const option = document.createElement('option');
        option.value = sym.value;
        option.innerText = sym.label;
        tradeSymbol.appendChild(option);
    });
    
    // Try to re-select previous value if active in the new mode
    if (symbols.some(s => s.value === selectedVal)) {
        tradeSymbol.value = selectedVal;
    } else {
        // Trigger widget update for new selection
        const tvSym = tvSymbolMap[tradeSymbol.value] || 'BINANCE:BTCUSDT';
        initTradingViewWidget(tvSym);
    }
}

// Render TradingView Widget Chart
function initTradingViewWidget(tvSymbol) {
    const container = document.getElementById('tradingview_widget');
    container.innerHTML = ''; // Clear container
    
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.type = 'text/javascript';
    script.async = true;
    script.onload = () => {
        if (typeof TradingView !== 'undefined') {
            tvWidget = new TradingView.widget({
                "autosize": true,
                "symbol": tvSymbol,
                "interval": "60",
                "timezone": "Etc/UTC",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "hide_side_toolbar": true,
                "allow_symbol_change": false,
                "container_id": "tradingview_widget"
            });
        }
    };
    document.head.appendChild(script);
}

// Fetch active positions
async function fetchPositions() {
    try {
        const res = await fetch('/api/positions');
        const positions = await res.json();
        
        posCount.innerText = positions.length;
        positionsList.innerHTML = '';
        
        if (positions.length === 0) {
            positionsList.innerHTML = '<div class="no-data">No open positions at the moment.</div>';
            return;
        }
        
        positions.forEach(pos => {
            const isLong = pos.direction === 'LONG';
            const card = document.createElement('div');
            card.className = `position-card glass ${isLong ? 'long' : 'short'}`;
            
            const pnl = Number(pos.floating_pnl);
            const pnlClass = pnl >= 0 ? 'pnl-profit' : 'pnl-loss';
            const pnlSign = pnl >= 0 ? '+' : '';
            
            card.innerHTML = `
                <div class="pos-header">
                    <div class="pos-title">
                        <span class="pos-symbol">${pos.symbol.replace('-USD', '').replace('USDT', '')}</span>
                        <span class="pos-dir ${isLong ? 'long' : 'short'}">${pos.direction}</span>
                    </div>
                    <div class="pos-pnl ${pnlClass}">${pnlSign}$${pnl.toFixed(2)} USD</div>
                </div>
                <div class="pos-grid">
                    <div class="pos-grid-item">
                        <span class="grid-label">Size</span>
                        <span class="grid-val">${pos.size.toLocaleString()}</span>
                    </div>
                    <div class="pos-grid-item">
                        <span class="grid-label">Entry Rate</span>
                        <span class="grid-val">${Number(pos.entry_price).toFixed(5)}</span>
                    </div>
                    <div class="pos-grid-item">
                        <span class="grid-label">Stop Loss</span>
                        <span class="grid-val">${Number(pos.stop_loss).toFixed(5)}</span>
                    </div>
                    <div class="pos-grid-item">
                        <span class="grid-label">Take Profit</span>
                        <span class="grid-val">${Number(pos.take_profit).toFixed(5)}</span>
                    </div>
                </div>
                <div class="pos-actions">
                    <button class="close-btn" onclick="handleClosePosition(${pos.position_id})">
                        <i class="fa-solid fa-rectangle-xmark"></i> Close Position
                    </button>
                </div>
            `;
            positionsList.appendChild(card);
        });
    } catch (e) {
        console.error('Failed to sync positions:', e);
    }
}

// Fetch closed trade history
async function fetchHistory() {
    try {
        const res = await fetch('/api/history');
        const history = await res.json();
        
        historyList.innerHTML = '';
        
        if (history.length === 0) {
            historyList.innerHTML = '<div class="no-data">No closed trades logged yet.</div>';
            return;
        }
        
        history.forEach(item => {
            const isWin = Number(item.pnl) >= 0;
            const pnlClass = isWin ? 'pnl-profit' : 'pnl-loss';
            const pnlSign = isWin ? '+' : '';
            
            const card = document.createElement('div');
            card.className = 'history-card glass';
            card.innerHTML = `
                <div class="hist-left">
                    <div class="hist-title">
                        <span class="hist-symbol">${item.symbol.replace('-USD', '').replace('USDT', '')}</span>
                        <span class="pos-dir ${item.direction.toLowerCase()}">${item.direction}</span>
                    </div>
                    <div class="hist-meta">Entry: ${Number(item.entry_price).toFixed(5)} | Exit: ${Number(item.exit_price).toFixed(5)}</div>
                </div>
                <div class="hist-right">
                    <div class="hist-pnl ${pnlClass}">${pnlSign}$${Number(item.pnl).toFixed(2)} USD</div>
                    <div class="hist-date">${item.closed_at ? item.closed_at.slice(0, 16).replace('T', ' ') : ''}</div>
                </div>
            `;
            historyList.appendChild(card);
        });
    } catch (e) {
        console.error('Failed to sync history:', e);
    }
}

// Fetch automated market scanner S/R levels
async function fetchScanData() {
    try {
        scanTableBody.innerHTML = '<tr><td colspan="6" class="no-data"><i class="fa-solid fa-spinner fa-spin"></i> Scanning markets...</td></tr>';
        
        const res = await fetch('/api/market-scan');
        const data = await res.json();
        
        scanTableBody.innerHTML = '';
        
        if (data.length === 0) {
            scanTableBody.innerHTML = '<tr><td colspan="6" class="no-data">No market data available.</td></tr>';
            return;
        }
        
        data.forEach(item => {
            const isBullish = item.trend === 'BULLISH';
            const supports = item.supports && item.supports.length > 0 ? item.supports.map(s => s.toFixed(2)).join(', ') : 'None';
            const resistances = item.resistances && item.resistances.length > 0 ? item.resistances.map(r => r.toFixed(2)).join(', ') : 'None';
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${item.symbol}</strong></td>
                <td>$${Number(item.spot).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                <td><span class="trend-badge ${isBullish ? 'bullish' : 'bearish'}">${item.trend}</span></td>
                <td>SMA20: $${item.sma_20.toFixed(2)}<br>SMA50: $${item.sma_50.toFixed(2)}</td>
                <td>${supports}</td>
                <td>${resistances}</td>
            `;
            scanTableBody.appendChild(row);
        });
    } catch (e) {
        console.error('Failed to sync scan:', e);
        scanTableBody.innerHTML = '<tr><td colspan="6" class="no-data">Error running market scan.</td></tr>';
    }
}

// Submit a proposed trade to AI auditor & execution pipeline
async function handleTradeSubmit(e) {
    e.preventDefault();
    
    const direction = document.querySelector('input[name="direction"]:checked').value;
    const bodyData = {
        symbol: tradeSymbol.value,
        direction: direction,
        entry: parseFloat(document.getElementById('tradeEntry').value),
        sl: parseFloat(document.getElementById('tradeSl').value),
        tp: parseFloat(document.getElementById('tradeTp').value),
        thesis: document.getElementById('tradeThesis').value
    };
    
    // Loading State
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Auditing Setup...';
    
    try {
        const res = await fetch('/api/trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyData)
        });
        
        const data = await res.json();
        
        if (res.ok) {
            // Show Feedback Modal
            showModal(data);
            
            if (data.success) {
                // Clear Form
                document.getElementById('tradeEntry').value = '';
                document.getElementById('tradeSl').value = '';
                document.getElementById('tradeTp').value = '';
                document.getElementById('tradeThesis').value = '';
                
                // Refresh open positions
                fetchPositions();
            }
        } else {
            alert(`Error: ${data.detail || 'Trade placement failed.'}`);
        }
        
    } catch (err) {
        console.error('Failed to submit trade:', err);
        alert('Network error. Failed to reach the bot manager server.');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-signature"></i> Submit Setup to Marcus';
    }
}

// Request position closure
async function handleClosePosition(positionId) {
    if (!confirm('Are you sure you want to close this position at the current market price?')) return;
    
    try {
        const res = await fetch('/api/close', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ position_id: positionId })
        });
        
        if (res.ok) {
            fetchPositions();
            fetchStatus();
        } else {
            const data = await res.json();
            alert(`Close Error: ${data.detail || 'Failed to close position.'}`);
        }
    } catch (e) {
        console.error('Failed to close position:', e);
    }
}

// Show AI Feedback Modal
function showModal(data) {
    const isApproved = data.decision === 'APPROVED';
    
    modalDecisionBadge.innerText = data.decision;
    modalDecisionBadge.className = `decision-badge ${isApproved ? 'approved' : 'rejected'}`;
    modalFeedbackText.innerText = data.feedback || 'No feedback received.';
    
    if (data.success) {
        modalTradeStats.style.display = 'flex';
        modalPosId.innerText = `#${data.position_id}`;
        modalSize.innerText = data.size.toLocaleString();
        modalRisk.innerText = `$${Number(data.risk_amount).toFixed(2)} USD`;
    } else {
        modalTradeStats.style.display = 'none';
        
        // If there are recommendations, suggest them
        if (data.suggested_sl || data.suggested_tp) {
            let sugMsg = '\n\n💡 Suggested adjustments:';
            if (data.suggested_sl) sugMsg += ` SL to ${data.suggested_sl}`;
            if (data.suggested_tp) sugMsg += ` TP to ${data.suggested_tp}`;
            modalFeedbackText.innerText += sugMsg;
        }
    }
    
    feedbackModal.classList.add('active');
}

function hideModal() {
    feedbackModal.classList.remove('active');
}


