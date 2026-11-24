/**
 * Zoqira Trading Terminal — Real-time Market Analysis & Signal Entry
 * Powered by Lightweight Charts & Zoqira AI Engine
 */

let currentSymbol = 'XAUUSD';
let currentTimeframe = '1h';
let mainChart = null;
let candleSeries = null;
let emaLines = {};
let priceLines = [];
let autoRefreshTimer = null;
let audioCtx = null;
let isSoundEnabled = true;
let lastTriggeredKey = '';

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    setupEventListeners();
    updateICTKillzone();
    setInterval(updateICTKillzone, 1000);
    await loadMarkets();
    await loadTickerTape();
    await loadMarketAnalysis(currentSymbol, currentTimeframe);
    await loadConfluence(currentSymbol);
    await loadDroppedSignalsFeed();

    // Auto-refresh every 30 seconds
    autoRefreshTimer = setInterval(() => {
        refreshCurrentData();
    }, 30000);
}

function setupEventListeners() {
    // Sound Toggle Button
    const soundBtn = document.getElementById('btn-sound-toggle');
    if (soundBtn) {
        soundBtn.addEventListener('click', () => {
            isSoundEnabled = !isSoundEnabled;
            const icon = document.getElementById('sound-icon');
            const text = document.getElementById('sound-text');
            if (isSoundEnabled) {
                soundBtn.classList.remove('muted');
                if (icon) icon.textContent = '🔊';
                if (text) text.textContent = 'SOUND ON';
                playChimeAlert();
            } else {
                soundBtn.classList.add('muted');
                if (icon) icon.textContent = '🔇';
                if (text) text.textContent = 'SOUND MUTED';
            }
        });
    }

    // Timeframe buttons
    document.querySelectorAll('.tf-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTimeframe = btn.dataset.tf;
            loadMarketAnalysis(currentSymbol, currentTimeframe);
        });
    });

    // Lot size calculator inputs
    const balanceInput = document.getElementById('calc-balance');
    const riskInput = document.getElementById('calc-risk');
    if (balanceInput && riskInput) {
        balanceInput.addEventListener('input', calculateLocalLotSize);
        riskInput.addEventListener('input', calculateLocalLotSize);
    }

    // Scan button & modal
    const scanBtn = document.getElementById('btn-open-scan');
    const modal = document.getElementById('scan-modal');
    const closeModal = document.getElementById('btn-close-modal');

    if (scanBtn && modal) {
        scanBtn.addEventListener('click', () => {
            modal.classList.add('active');
            runMarketScan();
        });
    }
    if (closeModal && modal) {
        closeModal.addEventListener('click', () => {
            modal.classList.remove('active');
        });
    }
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.remove('active');
        });
    }
}

// -------------------- 1. Markets & Ticker --------------------

async function loadMarkets() {
    try {
        const res = await fetch('/api/markets');
        const data = await res.json();
        if (data.status !== 'success') return;

        const container = document.getElementById('market-pills');
        if (!container) return;
        container.innerHTML = '';

        for (const [cat, symbols] of Object.entries(data.categories)) {
            symbols.forEach(m => {
                const pill = document.createElement('button');
                pill.className = `market-pill ${m.symbol === currentSymbol ? 'active' : ''}`;
                pill.dataset.symbol = m.symbol;
                pill.innerHTML = `<span>${m.emoji}</span> <span>${m.symbol}</span>`;
                pill.addEventListener('click', () => {
                    document.querySelectorAll('.market-pill').forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    currentSymbol = m.symbol;
                    loadMarketAnalysis(currentSymbol, currentTimeframe);
                    loadConfluence(currentSymbol);
                });
                container.appendChild(pill);
            });
        }
    } catch (err) {
        console.error('Error loading markets:', err);
    }
}

async function loadTickerTape() {
    try {
        const res = await fetch('/api/prices');
        const data = await res.json();
        if (data.status !== 'success' || !data.prices) return;

        const track = document.getElementById('ticker-track');
        if (!track) return;

        // Duplicate items for continuous seamless scroll
        const items = [...data.prices, ...data.prices];
        track.innerHTML = items.map(p => {
            const isUp = p.change_pct >= 0;
            const arrow = isUp ? '▲' : '▼';
            const cls = isUp ? 'up' : 'down';
            return `
                <div class="ticker-item" onclick="switchSymbol('${p.symbol}')">
                    <span class="sym">${p.emoji} ${p.symbol}</span>
                    <span class="price">$${p.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    <span class="change ${cls}">${arrow} ${p.change_pct >= 0 ? '+' : ''}${p.change_pct.toFixed(2)}%</span>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Error loading ticker tape:', err);
    }
}

function switchSymbol(symbol) {
    currentSymbol = symbol;
    document.querySelectorAll('.market-pill').forEach(pill => {
        if (pill.dataset.symbol === symbol) {
            pill.classList.add('active');
        } else {
            pill.classList.remove('active');
        }
    });
    loadMarketAnalysis(currentSymbol, currentTimeframe);
    loadConfluence(currentSymbol);
}

// -------------------- 2. Market Analysis & Signal Entry --------------------

let currentSignalData = null;

async function loadMarketAnalysis(symbol, tf) {
    try {
        const res = await fetch(`/api/analysis/${symbol}?timeframe=${tf}`);
        const data = await res.json();
        if (data.status !== 'success') {
            console.error(data.message);
            return;
        }

        currentSignalData = data;
        updateSignalHeroCard(data);
        updateTechnicalTable(data.indicators);
        updateReasoning(data);
        renderChart(data);
        calculateLocalLotSize();
    } catch (err) {
        console.error('Error loading analysis:', err);
    }
}

function updateSignalHeroCard(data) {
    const sig = data.signal;
    const heroCard = document.getElementById('signal-hero-card');

    // Header info
    document.getElementById('current-emoji').textContent = data.emoji || '📊';
    document.getElementById('current-symbol').textContent = data.symbol;
    document.getElementById('current-name').textContent = data.name;
    document.getElementById('current-price').textContent = `$${sig.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;

    // Action Badge
    const badge = document.getElementById('action-badge');
    badge.className = 'action-badge';
    heroCard.className = 'signal-hero-card';

    if (sig.direction === 'BUY') {
        badge.classList.add('buy');
        heroCard.classList.add('signal-buy');
        badge.innerHTML = `<span>🟢</span> <span>BUY / LONG (ទិញ)</span>`;
    } else if (sig.direction === 'SELL') {
        badge.classList.add('sell');
        heroCard.classList.add('signal-sell');
        badge.innerHTML = `<span>🔴</span> <span>SELL / SHORT (លក់)</span>`;
    } else {
        badge.classList.add('neutral');
        heroCard.classList.add('signal-neutral');
        badge.innerHTML = `<span>🟡</span> <span>WAIT / NEUTRAL (រង់ចាំ)</span>`;
    }

    // Confidence
    document.getElementById('conf-pct').textContent = `${sig.confidence}%`;
    document.getElementById('conf-fill').style.width = `${sig.confidence}%`;

    // 4 Key Metrics
    document.getElementById('lvl-entry').textContent = `$${sig.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;
    
    // Stop Loss
    const slEl = document.getElementById('lvl-sl');
    const slSub = document.getElementById('lvl-sl-sub');
    slEl.textContent = `$${sig.stop_loss.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;
    slSub.textContent = `Risk: -$${sig.risk_amount.toFixed(2)} (-${sig.risk_pct}%)`;

    // Take Profit
    const tpEl = document.getElementById('lvl-tp');
    const tpSub = document.getElementById('lvl-tp-sub');
    tpEl.textContent = `$${sig.take_profit_2.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;
    tpSub.textContent = `Target: +$${sig.reward_amount.toFixed(2)} (+${sig.reward_pct}%)`;

    // Risk / Reward
    const rrEl = document.getElementById('lvl-rr');
    const rrSub = document.getElementById('lvl-rr-sub');
    rrEl.textContent = `1 : ${sig.risk_reward}`;
    if (sig.risk_reward >= 2.0) {
        rrSub.textContent = '🟢 Excellent (ល្អណាស់)';
        rrSub.style.color = 'var(--color-green)';
    } else if (sig.risk_reward >= 1.5) {
        rrSub.textContent = '🟡 Good (ល្អបង្គួរ)';
        rrSub.style.color = 'var(--color-gold)';
    } else {
        rrSub.textContent = '🔴 High Risk (ហានិភ័យ)';
        rrSub.style.color = 'var(--color-red)';
    }

    // Multiple TP Targets
    document.getElementById('tp1-val').textContent = `$${sig.take_profit_1.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;
    document.getElementById('tp2-val').textContent = `$${sig.take_profit_2.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;
    document.getElementById('tp3-val').textContent = `$${sig.take_profit_3.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;

    // Optimal Entry Bar
    const oteRange = document.getElementById('ote-range');
    const oteTech = document.getElementById('ote-technique');
    const otePill = document.getElementById('ote-status-pill');
    const oteText = document.getElementById('ote-status-text');

    if (oteRange) {
        oteRange.textContent = `$${sig.optimal_entry_min.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})} — $${sig.optimal_entry_max.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;
    }
    if (oteTech) {
        oteTech.textContent = sig.entry_technique || 'Technical retracement zone';
    }
    if (otePill && oteText) {
        otePill.className = 'ote-status-pill';
        if (sig.is_optimal_now) {
            otePill.classList.add('ready');
            oteText.textContent = '🎯 READY TO ENTER (តម្លៃចូលល្អបំផុត!)';
        } else if (sig.direction === 'NEUTRAL') {
            otePill.classList.add('neutral');
            oteText.textContent = '⏸️ CONSOLIDATION';
        } else {
            otePill.classList.add('wait');
            oteText.textContent = '⏳ WAIT FOR RETRACEMENT';
        }
    }

    // Check Auto-Signal Trigger
    checkAndTriggerAutoSignal(data);
}

function updateTechnicalTable(indicators) {
    const tbody = document.getElementById('indicator-rows');
    if (!tbody || !indicators) return;

    tbody.innerHTML = '';
    const displayList = [
        { key: 'RSI', label: 'RSI (14)' },
        { key: 'MACD', label: 'MACD (12, 26, 9)' },
        { key: 'EMA', label: 'EMA Trend (9/21/50)' },
        { key: 'BB', label: 'Bollinger Bands' },
        { key: 'ADX', label: 'ADX (Trend Strength)' },
        { key: 'STOCH', label: 'Stochastic (14, 3)' },
        { key: 'VOLUME', label: 'Volume Flow' },
        { key: 'TREND_LONG', label: 'EMA 200 (Macro)' },
    ];

    displayList.forEach(item => {
        const data = indicators[item.key] || { signal: 'NEUTRAL', reason: 'N/A' };
        const sig = data.signal || 'NEUTRAL';
        let cls = 'neutral';
        let badgeText = 'NEUTRAL';

        if (sig === 'BUY') { cls = 'buy'; badgeText = 'BUY ▲'; }
        else if (sig === 'SELL') { cls = 'sell'; badgeText = 'SELL ▼'; }
        else if (sig === 'CONFIRM') { cls = 'buy'; badgeText = 'CONFIRMED ✓'; }

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="ind-name">
                <span>${item.label}</span>
            </td>
            <td class="ind-reason" style="color: var(--text-secondary); font-size: 0.76rem;">
                ${data.reason || ''}
            </td>
            <td class="ind-status ${cls}">
                ${badgeText}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function updateReasoning(data) {
    const box = document.getElementById('ai-reasoning-box');
    if (!box) return;

    const sig = data.signal;
    let reasonsHtml = '';
    if (sig.key_reasons && sig.key_reasons.length > 0) {
        reasonsHtml = `
            <ul class="reasons-list">
                ${sig.key_reasons.map(r => `<li><span>⚡</span> <span>${r}</span></li>`).join('')}
            </ul>
        `;
    }

    box.innerHTML = `
        <p style="color: var(--text-primary); font-weight: 600;">${sig.summary_kh}</p>
        <p style="font-size: 0.78rem; color: var(--text-muted);">${sig.summary_en}</p>
        ${reasonsHtml}
    `;
}

// -------------------- 3. Confluence --------------------

async function loadConfluence(symbol) {
    try {
        const res = await fetch(`/api/confluence/${symbol}`);
        const data = await res.json();
        if (data.status !== 'success') return;

        const container = document.getElementById('confluence-grid');
        if (!container) return;
        container.innerHTML = '';

        const tfs = ['15m', '1h', '4h', '1d'];
        tfs.forEach(tf => {
            const tfData = data.timeframes[tf] || { direction: 'NEUTRAL', confidence: 50 };
            const dir = tfData.direction;
            const cls = dir === 'BUY' ? 'buy' : dir === 'SELL' ? 'sell' : 'neutral';
            const icon = dir === 'BUY' ? '▲ BUY' : dir === 'SELL' ? '▼ SELL' : '● WAIT';

            const box = document.createElement('div');
            box.className = 'conf-tf-box';
            box.innerHTML = `
                <div class="tf-name">${tf.toUpperCase()}</div>
                <div class="tf-signal ${cls}">${icon}</div>
                <div class="tf-rsi">${tfData.confidence}% conf</div>
            `;
            container.appendChild(box);
        });
    } catch (err) {
        console.error('Error loading confluence:', err);
    }
}

// -------------------- 4. Position Sizing / Lot Calculator --------------------

function calculateLocalLotSize() {
    if (!currentSignalData) return;
    const balance = parseFloat(document.getElementById('calc-balance')?.value || 1000);
    const riskPct = parseFloat(document.getElementById('calc-risk')?.value || 2);
    const sig = currentSignalData.signal;

    const riskDollar = balance * (riskPct / 100);
    const slDist = Math.abs(sig.entry_price - sig.stop_loss);

    let lotSize = 0.01;
    const sym = currentSignalData.symbol.toUpperCase();

    if (sym.includes('XAU') || sym.includes('GC')) {
        // 1 lot gold = 100 oz ($100 per $1 move)
        const dollarPerLot = slDist * 100;
        lotSize = dollarPerLot > 0 ? (riskDollar / dollarPerLot) : 0.01;
    } else if (sym.includes('EUR') || sym.includes('GBP') || sym.includes('USD') || sym.includes('JPY') || sym.includes('AUD')) {
        const pipSize = sym.includes('JPY') ? 0.01 : 0.0001;
        const pips = slDist / pipSize;
        lotSize = pips > 0 ? (riskDollar / (pips * 10)) : 0.01;
    } else if (sym.includes('BTC') || sym.includes('ETH')) {
        lotSize = slDist > 0 ? (riskDollar / slDist) : 0.01;
    } else {
        lotSize = slDist > 0 ? (riskDollar / slDist) : 1.0;
    }

    const finalLot = Math.max(parseFloat(lotSize.toFixed(2)), 0.01);
    document.getElementById('res-lot').textContent = `${finalLot} Lots`;
    document.getElementById('res-risk-dollar').textContent = `-$${riskDollar.toFixed(2)}`;
}

// -------------------- 5. Chart Rendering (TradingView Lightweight Charts) --------------------

function renderChart(data) {
    const container = document.getElementById('chart-container');
    if (!container) return;

    if (!window.LightweightCharts) {
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">TradingView Chart Engine loading...</div>';
        return;
    }

    // Reset container if chart exists
    if (mainChart) {
        try {
            mainChart.remove();
        } catch (e) {
            console.warn('Error removing old chart:', e);
        }
        mainChart = null;
        candleSeries = null;
        priceLines = [];
    }

    container.innerHTML = '';

    const chartWidth = container.clientWidth || container.parentElement?.clientWidth || 800;
    const chartHeight = 440;

    mainChart = LightweightCharts.createChart(container, {
        width: chartWidth,
        height: chartHeight,
        layout: {
            background: { color: '#0f1523' },
            textColor: '#8da2bb',
            fontFamily: "'JetBrains Mono', monospace",
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: '#1f2b42',
            autoScale: true,
            scaleMargins: {
                top: 0.1,
                bottom: 0.15,
            },
        },
        timeScale: {
            borderColor: '#1f2b42',
            timeVisible: true,
            secondsVisible: false,
            rightOffset: 12,
            barSpacing: 8,
        },
    });

    const candleOpts = {
        upColor: '#00f59b',
        downColor: '#ff3b57',
        borderUpColor: '#00f59b',
        borderDownColor: '#ff3b57',
        wickUpColor: '#00f59b',
        wickDownColor: '#ff3b57',
    };

    if (typeof mainChart.addCandlestickSeries === 'function') {
        candleSeries = mainChart.addCandlestickSeries(candleOpts);
    } else if (typeof mainChart.addSeries === 'function' && LightweightCharts.CandlestickSeries) {
        candleSeries = mainChart.addSeries(LightweightCharts.CandlestickSeries, candleOpts);
    }

    // Filter and sort candles
    if (candleSeries && data.candles && data.candles.length > 0) {
        const sortedCandles = data.candles
            .filter(c => c && typeof c.time === 'number' && !isNaN(c.close))
            .sort((a, b) => a.time - b.time);

        // Deduplicate timestamps if any
        const uniqueCandles = [];
        let lastTime = -1;
        for (const c of sortedCandles) {
            if (c.time > lastTime) {
                uniqueCandles.push(c);
                lastTime = c.time;
            }
        }

        candleSeries.setData(uniqueCandles);
    }

    // Helper for line series
    function addLine(opts) {
        if (typeof mainChart.addLineSeries === 'function') {
            return mainChart.addLineSeries(opts);
        } else if (typeof mainChart.addSeries === 'function' && LightweightCharts.LineSeries) {
            return mainChart.addSeries(LightweightCharts.LineSeries, opts);
        }
        return null;
    }

    // Moving Averages Overlays
    if (data.overlays) {
        if (data.overlays.ema_21 && data.overlays.ema_21.length > 0) {
            const ema21 = addLine({ color: '#00d4ff', lineWidth: 1.5, title: 'EMA 21' });
            if (ema21) {
                const clean = data.overlays.ema_21.filter(p => !isNaN(p.value)).sort((a,b)=>a.time-b.time);
                ema21.setData(clean);
            }
        }
        if (data.overlays.ema_50 && data.overlays.ema_50.length > 0) {
            const ema50 = addLine({ color: '#ffb703', lineWidth: 1.5, title: 'EMA 50' });
            if (ema50) {
                const clean = data.overlays.ema_50.filter(p => !isNaN(p.value)).sort((a,b)=>a.time-b.time);
                ema50.setData(clean);
            }
        }
        if (data.overlays.ema_200 && data.overlays.ema_200.length > 0) {
            const ema200 = addLine({ color: '#9d4edd', lineWidth: 2, title: 'EMA 200' });
            if (ema200) {
                const clean = data.overlays.ema_200.filter(p => !isNaN(p.value)).sort((a,b)=>a.time-b.time);
                ema200.setData(clean);
            }
        }
    }

    // Horizontal Entry / SL / TP Price Lines
    const sig = data.signal;
    if (candleSeries && sig && sig.direction !== 'NEUTRAL') {
        try {
            // Entry Line (Cyan)
            candleSeries.createPriceLine({
                price: sig.entry_price,
                color: '#00d4ff',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'ENTRY (ចូល)',
            });

            // Stop Loss Line (Red)
            candleSeries.createPriceLine({
                price: sig.stop_loss,
                color: '#ff3b57',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'SL (កាត់ខាត)',
            });

            // TP 1 Line (Green)
            candleSeries.createPriceLine({
                price: sig.take_profit_1,
                color: '#00f59b',
                lineWidth: 1.5,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: 'TP 1',
            });

            // TP 2 Line (Green solid)
            candleSeries.createPriceLine({
                price: sig.take_profit_2,
                color: '#00f59b',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'TP 2 (TARGET)',
            });

            // TP 3 Line (Green)
            candleSeries.createPriceLine({
                price: sig.take_profit_3,
                color: '#00f59b',
                lineWidth: 1.5,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: 'TP 3 (MAX)',
            });

            // OTE Target Line (Gold Dashed)
            if (sig.optimal_entry_target) {
                candleSeries.createPriceLine({
                    price: sig.optimal_entry_target,
                    color: '#ffb703',
                    lineWidth: 1.5,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: 'OTE (ចូលល្អបំផុត)',
                });
            }
        } catch (e) {
            console.warn('Price lines error:', e);
        }
    }

    // Auto-fit content so candles are clearly visible immediately
    try {
        mainChart.timeScale().fitContent();
    } catch (e) {
        console.warn('fitContent error:', e);
    }
}

// -------------------- 6. Market Scanner --------------------

async function runMarketScan() {
    const tbody = document.getElementById('scan-table-body');
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2rem; color: var(--text-secondary);">⚡ កំពុងស្កេន XAUUSD និង BTCUSD... សូមរង់ចាំ (Scanning XAUUSD & BTCUSD)...</td></tr>`;

    try {
        const res = await fetch('/api/scan');
        const data = await res.json();
        if (data.status !== 'success' || !data.opportunities) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--color-red);">បរាជ័យក្នុងការស្កេន (Scan failed).</td></tr>`;
            return;
        }

        tbody.innerHTML = data.opportunities.map((opp, idx) => {
            const cls = opp.direction === 'BUY' ? 'buy' : opp.direction === 'SELL' ? 'sell' : 'neutral';
            return `
                <tr onclick="selectScanResult('${opp.symbol}')">
                    <td><strong>#${idx + 1}</strong></td>
                    <td>
                        <span style="font-size: 1.1rem; margin-right: 0.3rem;">${opp.emoji}</span>
                        <strong>${opp.symbol}</strong>
                        <div style="font-size: 0.72rem; color: var(--text-muted);">${opp.name}</div>
                    </td>
                    <td><span class="scan-badge ${cls}">${opp.direction}</span></td>
                    <td><strong>${opp.confidence}%</strong></td>
                    <td>$${opp.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}</td>
                    <td style="color: var(--color-gold);">1 : ${opp.risk_reward}</td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--color-red);">Error: ${err.message}</td></tr>`;
    }
}

function selectScanResult(symbol) {
    const modal = document.getElementById('scan-modal');
    if (modal) modal.classList.remove('active');
    switchSymbol(symbol);
}

// -------------------- 7. Background Auto-refresh --------------------

function refreshCurrentData() {
    loadTickerTape();
    loadMarketAnalysis(currentSymbol, currentTimeframe);
}

// -------------------- 8. ICT Kill Zone Real-Time Tracker --------------------

function updateICTKillzone() {
    const now = new Date();
    // Convert to GMT+7 (Cambodia Time)
    const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
    const khTime = new Date(utc + (3600000 * 7));

    const hours = khTime.getHours();
    const minutes = khTime.getMinutes();
    const seconds = khTime.getSeconds();
    const totalMins = hours * 60 + minutes;

    const timeStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')} (GMT+7)`;
    const clockEl = document.getElementById('ict-clock');
    if (clockEl) clockEl.textContent = timeStr;

    const badge = document.getElementById('ict-zone-badge');
    const nameEl = document.getElementById('ict-zone-name');
    const advisoryTitle = document.getElementById('advisory-title');
    const advisoryDesc = document.getElementById('advisory-desc');
    const advisoryBadge = document.getElementById('advisory-badge');
    const advisoryIcon = document.getElementById('advisory-icon');

    if (!badge || !nameEl) return;

    // Reset base classes
    badge.className = 'ict-zone-pill';
    if (advisoryBadge) advisoryBadge.className = 'advisory-badge';

    // Check Killzones
    if (totalMins >= 1110 && totalMins < 1320) {
        // New York Open Killzone (18:30 - 22:00)
        badge.classList.add('ny-active');
        nameEl.textContent = '🟢 NY OPEN KILLZONE (18:30 - 22:00)';
        if (advisoryTitle) advisoryTitle.textContent = '🔥 NEW YORK OPEN KILLZONE — ម៉ោងមាសលេខ ១ សម្រាប់ XAUUSD & BTCUSD';
        if (advisoryDesc) advisoryDesc.textContent = 'Peak Volume & Liquidity! ស្ថាប័ន Wall Street កំពុងដំណើរការ — ពេលវេលាល្អបំផុតក្នុងការ Scan និងចូល Trade!';
        if (advisoryBadge) {
            advisoryBadge.classList.add('optimal');
            advisoryBadge.textContent = 'OPTIMAL TIME TO SCAN';
        }
        if (advisoryIcon) advisoryIcon.textContent = '🔥';
    } else if (totalMins >= 810 && totalMins < 990) {
        // London Open Killzone (13:30 - 16:30)
        badge.classList.add('london-active');
        nameEl.textContent = '⚡ LONDON OPEN KILLZONE (13:30 - 16:30)';
        if (advisoryTitle) advisoryTitle.textContent = '⚡ LONDON OPEN KILLZONE — ស្ថាប័នអឺរ៉ុបកំពុងធ្វើសកម្មភាព';
        if (advisoryDesc) advisoryDesc.textContent = 'High Volatility! ទីផ្សារកំពុងបង្កើត High/Low នៃថ្ងៃ (ប្រយ័ត្ន Judas Swing នៅ ៣០ នាទីដំបូង រួចសឹម Scan)។';
        if (advisoryBadge) {
            advisoryBadge.classList.add('active-zone');
            advisoryBadge.textContent = 'HIGH VOLATILITY';
        }
        if (advisoryIcon) advisoryIcon.textContent = '⚡';
    } else if (totalMins >= 1320 && totalMins < 1410) {
        // London Close Killzone (22:00 - 23:30)
        badge.classList.add('london-close-active');
        nameEl.textContent = '🎯 LONDON CLOSE KILLZONE (21:30 - 23:30)';
        if (advisoryTitle) advisoryTitle.textContent = '🎯 LONDON CLOSE KILLZONE — ម៉ោងទូទាត់ប្រាក់ចំណេញរបស់អឺរ៉ុប';
        if (advisoryDesc) advisoryDesc.textContent = 'London Profit Taking! ទីផ្សារអាចមានការទាញថយក្រោយ (Retracement) មុនពេលបន្ត Trend។';
        if (advisoryBadge) {
            advisoryBadge.classList.add('active-zone');
            advisoryBadge.textContent = 'PROFIT TAKING';
        }
        if (advisoryIcon) advisoryIcon.textContent = '🎯';
    } else if (totalMins >= 420 && totalMins < 660) {
        // Asian Consolidation (07:00 - 11:00)
        badge.classList.add('asian-active');
        nameEl.textContent = '💤 ASIAN CONSOLIDATION (07:00 - 11:00)';
        if (advisoryTitle) advisoryTitle.textContent = '💤 ASIAN CONSOLIDATION — ទីផ្សារដើរ Sideway / Range';
        if (advisoryDesc) advisoryDesc.textContent = 'គ្មាន Volume ធំទេ ទីផ្សារកំពុងបង្កើតអន្ទាក់ Liquidity Pool — គួររង់ចាំ London Open (ម៉ោង 13:30)។';
        if (advisoryBadge) {
            advisoryBadge.classList.add('wait');
            advisoryBadge.textContent = 'RANGE / SIDEWAY';
        }
        if (advisoryIcon) advisoryIcon.textContent = '💤';
    } else {
        // Outside Killzone
        badge.classList.add('outside-zone');

        let nextZoneName = '';
        let minsUntil = 0;

        if (totalMins < 420) {
            nextZoneName = 'Asian Session (07:00)';
            minsUntil = 420 - totalMins;
        } else if (totalMins < 810) {
            nextZoneName = 'London Open (13:30)';
            minsUntil = 810 - totalMins;
        } else if (totalMins < 1110) {
            nextZoneName = 'NY Open (18:30)';
            minsUntil = 1110 - totalMins;
        } else {
            nextZoneName = 'Asian Session (ស្អែក 07:00)';
            minsUntil = (1440 - totalMins) + 420;
        }

        const remH = Math.floor(minsUntil / 60);
        const remM = minsUntil % 60;
        const countdownStr = remH > 0 ? `${remH}h ${remM}m` : `${remM}m`;

        nameEl.textContent = `⚪ OUTSIDE ZONE (Next: ${nextZoneName} in ${countdownStr})`;
        if (advisoryTitle) advisoryTitle.textContent = `⏳ OUTSIDE ICT KILL ZONE — រង់ចាំ ${nextZoneName}`;
        if (advisoryDesc) advisoryDesc.textContent = `ទីផ្សារសម្រាករវាង Session (នៅសល់ ${countdownStr})។ គួររង់ចាំដល់ម៉ោង Killzone ទើបចុច Scan ដើម្បីកាត់បន្ថយ Hit SL!`;
        if (advisoryBadge) {
            advisoryBadge.classList.add('wait');
            advisoryBadge.textContent = `WAIT (${countdownStr})`;
        }
        if (advisoryIcon) advisoryIcon.textContent = '⏳';
    }
}

// -------------------- 9. Audio Synthesizer & Auto-Signal Trigger Engine --------------------

function playChimeAlert() {
    if (!isSoundEnabled) return;
    try {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }

        const now = audioCtx.currentTime;

        // Tone 1: 1318.5 Hz (E6)
        const osc1 = audioCtx.createOscillator();
        const gain1 = audioCtx.createGain();
        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(1318.5, now);
        gain1.gain.setValueAtTime(0.2, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
        osc1.connect(gain1);
        gain1.connect(audioCtx.destination);
        osc1.start(now);
        osc1.stop(now + 0.5);

        // Tone 2: 1760 Hz (A6)
        const osc2 = audioCtx.createOscillator();
        const gain2 = audioCtx.createGain();
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(1760.0, now + 0.1);
        gain2.gain.setValueAtTime(0.25, now + 0.1);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.8);
        osc2.connect(gain2);
        gain2.connect(audioCtx.destination);
        osc2.start(now + 0.1);
        osc2.stop(now + 0.8);
    } catch (e) {
        console.warn('Audio chime warning:', e);
    }
}

function checkAndTriggerAutoSignal(data) {
    const sig = data.signal;
    if (!sig || sig.direction === 'NEUTRAL') return;

    // Trigger when price enters optimal entry zone
    if (sig.is_optimal_now) {
        const triggerKey = `${data.symbol}_${sig.direction}_${Math.round(sig.entry_price)}`;
        if (lastTriggeredKey !== triggerKey) {
            lastTriggeredKey = triggerKey;

            // 1. Play Audio Chime Sound
            playChimeAlert();

            // 2. Pop up Toast Notification
            showSignalToast(data);

            // 3. Reload Dropped Signals Feed
            setTimeout(loadDroppedSignalsFeed, 1000);
        }
    }
}

function showSignalToast(data) {
    const toast = document.getElementById('auto-signal-toast');
    if (!toast) return;

    const sig = data.signal;
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;

    const timeEl = document.getElementById('toast-time');
    const symEl = document.getElementById('toast-symbol');
    const actEl = document.getElementById('toast-action');
    const detEl = document.getElementById('toast-details');

    if (timeEl) timeEl.textContent = timeStr;
    if (symEl) symEl.textContent = `${data.emoji} ${data.symbol}`;
    if (actEl) {
        actEl.textContent = `${sig.direction} @ $${sig.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4})}`;
        actEl.style.color = sig.direction === 'BUY' ? 'var(--color-green)' : 'var(--color-red)';
    }
    if (detEl) {
        detEl.textContent = `SL: $${sig.stop_loss.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} | TP: $${sig.take_profit_2.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} (R:R 1:${sig.risk_reward})`;
    }

    toast.className = `auto-signal-toast show ${sig.direction === 'BUY' ? 'toast-buy' : 'toast-sell'}`;

    // Auto-hide after 8 seconds
    setTimeout(() => {
        toast.classList.remove('show');
    }, 8000);
}

async function loadDroppedSignalsFeed() {
    const container = document.getElementById('dropped-signals-list');
    if (!container) return;

    try {
        const res = await fetch('/api/signals_feed');
        const data = await res.json();
        if (data.status !== 'success' || !data.feed || data.feed.length === 0) {
            return;
        }

        container.innerHTML = data.feed.map(item => {
            const isBuy = item.direction === 'BUY';
            const cls = isBuy ? 'buy' : 'sell';
            return `
                <div class="dropped-signal-card ${cls}" onclick="switchSymbol('${item.symbol}')" style="cursor: pointer;">
                    <div class="dropped-sig-top">
                        <span class="dropped-sig-symbol">${item.emoji} ${item.symbol}</span>
                        <span class="dropped-sig-time">⏱ ${item.time}</span>
                    </div>
                    <div class="dropped-sig-mid">
                        <span class="dropped-sig-action ${cls}">${item.direction} @ $${item.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                        <span class="dropped-sig-rr">R:R 1:${item.risk_reward}</span>
                    </div>
                    <div class="dropped-sig-levels">
                        <span style="color: var(--color-red);">SL: $${item.stop_loss.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                        <span style="color: var(--color-green);">TP: $${item.take_profit.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.warn('Error loading signal feed:', e);
    }
}
