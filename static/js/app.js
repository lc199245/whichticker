/* ── WhichTicker — Frontend ────────────────────────────────────────────────── */

// State
let charts = {};    // Chart.js instances (keyed by canvas ID)
let isAnalyzing = false;

// Chart.js dark theme defaults
const COLORS = {
    bg:       '#161922',
    grid:     '#1c1f2e',
    text:     '#9ca3af',
    accent:   '#3b82f6',
    gain:     '#22c55e',
    loss:     '#ef4444',
    warn:     '#eab308',
    orange:   '#f97316',
    purple:   '#a855f7',
    cyan:     '#06b6d4',
    white:    '#e5e7eb',
};

const FONT = { family: "'Inter', sans-serif" };

// ── Main Analysis Function ──────────────────────────────────────────────────

async function analyzePair() {
    if (isAnalyzing) return;

    const tickerA = document.getElementById('input-ticker-a').value.trim().toUpperCase();
    const tickerB = document.getElementById('input-ticker-b').value.trim().toUpperCase();
    const period  = document.getElementById('input-period').value;

    // Validate
    const errEl = document.getElementById('error-msg');
    errEl.classList.add('hidden');

    if (!tickerA || !tickerB) {
        showError('Please enter both tickers.');
        return;
    }
    if (tickerA === tickerB) {
        showError('Tickers must be different.');
        return;
    }

    isAnalyzing = true;
    document.getElementById('results').classList.add('hidden');
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('analyze-btn').disabled = true;
    document.getElementById('analyze-btn').classList.add('opacity-50');

    try {
        const resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker_a: tickerA, ticker_b: tickerB, period }),
        });

        const data = await resp.json();

        if (!resp.ok || data.error) {
            showError(data.error || `Server returned ${resp.status}`);
            return;
        }

        renderResults(data);
    } catch (err) {
        showError(`Analysis failed: ${err.message}`);
    } finally {
        isAnalyzing = false;
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('analyze-btn').disabled = false;
        document.getElementById('analyze-btn').classList.remove('opacity-50');
    }
}

// ── Render All Results ──────────────────────────────────────────────────────

function renderResults(data) {
    const resultsEl = document.getElementById('results');

    // Destroy all existing charts
    Object.keys(charts).forEach(destroyChart);

    // Price charts
    renderPriceChart('chart-price-a', data.ticker_a, COLORS.accent);
    renderPriceChart('chart-price-b', data.ticker_b, COLORS.purple);
    document.getElementById('chart-a-title').textContent = `${data.ticker_a.symbol} — ${data.ticker_a.name}`;
    document.getElementById('chart-b-title').textContent = `${data.ticker_b.symbol} — ${data.ticker_b.name}`;

    // Price Ratio + MAs
    renderRatioChart('chart-ratio', data);

    // Cumulative Returns Comparison
    renderReturnsChart('chart-returns', data);

    // Z-Score
    renderZScoreChart('chart-zscore', data);

    // Statistics grid
    renderStatistics(data.statistics, data.ticker_a.symbol, data.ticker_b.symbol);

    // RSI
    renderRSIChart('chart-rsi', data);

    // MACD
    renderMACDChart('chart-macd', data);

    // Technical confirmation badges
    renderTechSignals(data.technicals.confirmation);

    // Signal banner
    renderSignalBanner(data.combined || data.signal, data.ticker_a.symbol, data.ticker_b.symbol);

    // AI recommendation
    renderAIRecommendation(data.ai_recommendation);

    // Show results
    resultsEl.classList.remove('hidden');

    // Save to history
    const combined = data.combined || data.signal || {};
    addToHistory(
        data.ticker_a.symbol,
        data.ticker_b.symbol,
        document.getElementById('input-period').value,
        combined.direction || 'NEUTRAL',
        combined.conviction || 0,
    );

    // Re-init lucide icons for any new elements
    lucide.createIcons();
}

// ── Price Chart ─────────────────────────────────────────────────────────────

function renderPriceChart(canvasId, tickerData, color) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const dates  = tickerData.dates || [];
    const prices = tickerData.prices || [];

    const labels = thinLabels(dates, 8);

    charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: tickerData.symbol,
                data: prices,
                borderColor: color,
                backgroundColor: hexToRgba(color, 0.1),
                borderWidth: 1.5,
                pointRadius: 0,
                fill: true,
                tension: 0.3,
            }],
        },
        options: {
            ...baseChartOptions(),
            scales: {
                x: { ...baseXScale(labels) },
                y: { ...baseYScale() },
            },
        },
    });
}

// ── Price Ratio + Moving Averages Chart ─────────────────────────────────────

function renderRatioChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const dates  = data.ratio.dates;
    const labels = thinLabels(dates, 10);

    const datasets = [
        {
            label: 'Price Ratio (A/B)',
            data: data.ratio.values,
            borderColor: COLORS.accent,
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            tension: 0.2,
            order: 1,
        },
        {
            label: '50d MA',
            data: data.ratio.ma_50,
            borderColor: COLORS.orange,
            borderWidth: 1.5,
            borderDash: [6, 3],
            pointRadius: 0,
            fill: false,
            tension: 0.2,
            order: 2,
        },
        {
            label: '200d MA',
            data: data.ratio.ma_200,
            borderColor: COLORS.purple,
            borderWidth: 1.5,
            borderDash: [6, 3],
            pointRadius: 0,
            fill: false,
            tension: 0.2,
            order: 3,
        },
    ];

    // Also show Bollinger Bands on the ratio
    if (data.technicals && data.technicals.bollinger) {
        datasets.push({
            label: 'BB Upper',
            data: data.technicals.bollinger.upper,
            borderColor: hexToRgba(COLORS.loss, 0.4),
            borderWidth: 1,
            borderDash: [3, 3],
            pointRadius: 0,
            fill: false,
            tension: 0.2,
            order: 4,
        });
        datasets.push({
            label: 'BB Lower',
            data: data.technicals.bollinger.lower,
            borderColor: hexToRgba(COLORS.gain, 0.4),
            borderWidth: 1,
            borderDash: [3, 3],
            pointRadius: 0,
            fill: '-1',
            backgroundColor: hexToRgba(COLORS.accent, 0.03),
            tension: 0.2,
            order: 5,
        });
    }

    charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: { labels: dates, datasets },
        options: {
            ...baseChartOptions(),
            scales: {
                x: { ...baseXScale(labels) },
                y: { ...baseYScale() },
            },
        },
    });
}

// ── Cumulative Returns Comparison Chart ──────────────────────────────────────

function renderReturnsChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const dates  = data.returns.dates;
    const labels = thinLabels(dates, 10);

    charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                {
                    label: data.ticker_a.symbol,
                    data: data.returns.returns_a,
                    borderColor: COLORS.accent,
                    backgroundColor: hexToRgba(COLORS.accent, 0.05),
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.2,
                },
                {
                    label: data.ticker_b.symbol,
                    data: data.returns.returns_b,
                    borderColor: COLORS.purple,
                    backgroundColor: hexToRgba(COLORS.purple, 0.05),
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.2,
                },
            ],
        },
        options: {
            ...baseChartOptions(),
            scales: {
                x: { ...baseXScale(labels) },
                y: {
                    ...baseYScale(),
                    ticks: {
                        ...baseYScale().ticks,
                        callback: function(val) { return val.toFixed(1) + '%'; },
                    },
                },
            },
            plugins: {
                ...baseChartOptions().plugins,
                annotation: {
                    annotations: {
                        zero: {
                            type: 'line', yMin: 0, yMax: 0,
                            borderColor: COLORS.white, borderWidth: 0.5,
                        },
                    },
                },
            },
        },
    });
}

// ── Z-Score Chart ───────────────────────────────────────────────────────────

function renderZScoreChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const dates  = data.zscore.dates;
    const labels = thinLabels(dates, 10);

    charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Ratio Z-Score',
                data: data.zscore.values,
                borderColor: COLORS.cyan,
                borderWidth: 1.5,
                pointRadius: 0,
                fill: false,
                tension: 0.2,
            }],
        },
        options: {
            ...baseChartOptions(),
            scales: {
                x: { ...baseXScale(labels) },
                y: { ...baseYScale() },
            },
            plugins: {
                ...baseChartOptions().plugins,
                annotation: {
                    annotations: {
                        upper2: {
                            type: 'line', yMin: 2, yMax: 2,
                            borderColor: COLORS.loss, borderWidth: 1, borderDash: [4, 4],
                            label: { display: true, content: '+2σ', position: 'start',
                                     font: { size: 9, family: FONT.family }, color: COLORS.loss,
                                     backgroundColor: 'transparent' },
                        },
                        upper1: {
                            type: 'line', yMin: 1, yMax: 1,
                            borderColor: COLORS.warn, borderWidth: 0.8, borderDash: [3, 3],
                        },
                        zero: {
                            type: 'line', yMin: 0, yMax: 0,
                            borderColor: COLORS.white, borderWidth: 0.5,
                        },
                        lower1: {
                            type: 'line', yMin: -1, yMax: -1,
                            borderColor: COLORS.warn, borderWidth: 0.8, borderDash: [3, 3],
                        },
                        lower2: {
                            type: 'line', yMin: -2, yMax: -2,
                            borderColor: COLORS.gain, borderWidth: 1, borderDash: [4, 4],
                            label: { display: true, content: '-2σ', position: 'start',
                                     font: { size: 9, family: FONT.family }, color: COLORS.gain,
                                     backgroundColor: 'transparent' },
                        },
                    },
                },
            },
        },
    });
}

// ── RSI Chart ───────────────────────────────────────────────────────────────

function renderRSIChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const dates  = data.ratio.dates;
    const labels = thinLabels(dates, 8);

    charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'RSI (Ratio)',
                data: data.technicals.rsi.values,
                borderColor: COLORS.orange,
                borderWidth: 1.5,
                pointRadius: 0,
                fill: false,
                tension: 0.2,
            }],
        },
        options: {
            ...baseChartOptions(),
            scales: {
                x: { ...baseXScale(labels) },
                y: { ...baseYScale(), min: 0, max: 100 },
            },
            plugins: {
                ...baseChartOptions().plugins,
                annotation: {
                    annotations: {
                        overbought: {
                            type: 'line', yMin: 70, yMax: 70,
                            borderColor: COLORS.loss, borderWidth: 1, borderDash: [4, 4],
                            label: { display: true, content: 'Overbought (70)', position: 'start',
                                     font: { size: 9, family: FONT.family }, color: COLORS.loss,
                                     backgroundColor: 'transparent' },
                        },
                        oversold: {
                            type: 'line', yMin: 30, yMax: 30,
                            borderColor: COLORS.gain, borderWidth: 1, borderDash: [4, 4],
                            label: { display: true, content: 'Oversold (30)', position: 'start',
                                     font: { size: 9, family: FONT.family }, color: COLORS.gain,
                                     backgroundColor: 'transparent' },
                        },
                        midline: {
                            type: 'line', yMin: 50, yMax: 50,
                            borderColor: COLORS.text, borderWidth: 0.5, borderDash: [2, 4],
                        },
                    },
                },
            },
        },
    });
}

// ── MACD Chart ──────────────────────────────────────────────────────────────

function renderMACDChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const dates  = data.ratio.dates;
    const labels = thinLabels(dates, 8);
    const histogram = data.technicals.macd.histogram;

    const histColors = histogram.map(v => v === null ? COLORS.text : (v >= 0 ? COLORS.gain : COLORS.loss));

    charts[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: dates,
            datasets: [
                {
                    label: 'Histogram',
                    data: histogram,
                    backgroundColor: histColors,
                    borderWidth: 0,
                    order: 2,
                    barPercentage: 0.6,
                },
                {
                    type: 'line',
                    label: 'MACD',
                    data: data.technicals.macd.macd_line,
                    borderColor: COLORS.accent,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.2,
                    order: 1,
                },
                {
                    type: 'line',
                    label: 'Signal',
                    data: data.technicals.macd.signal_line,
                    borderColor: COLORS.orange,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.2,
                    order: 1,
                },
            ],
        },
        options: {
            ...baseChartOptions(),
            scales: {
                x: { ...baseXScale(labels) },
                y: { ...baseYScale() },
            },
        },
    });
}

// ── Statistics Grid ─────────────────────────────────────────────────────────

function renderStatistics(stats, symbolA, symbolB) {
    const grid = document.getElementById('stats-grid');
    const coint = stats.cointegration || {};
    const relRet = stats.relative_returns || {};

    // Find the best available return differential
    const retPeriods = ['1mo', '3mo', '6mo'];
    let retDiffLabel = '';
    let retDiffVal = null;
    for (const p of retPeriods) {
        if (relRet[p] && relRet[p].differential !== null) {
            retDiffLabel = `Return Diff (${p})`;
            retDiffVal = relRet[p].differential;
            break;
        }
    }

    // Color logic: green = favors A, red = favors B, neutral = inconclusive
    const metrics = [
        {
            label: 'Current Ratio (A/B)',
            value: fmt(stats.current_ratio, 4),
            cls: 'stat-neutral',
            tip: `Price of ${symbolA} divided by ${symbolB}. A rising ratio means ${symbolA} is outperforming. A falling ratio means ${symbolB} is outperforming.`,
        },
        {
            label: `Ratio vs 50d MA`,
            value: stats.ratio_above_ma_50 === true ? 'Above ↑' : stats.ratio_above_ma_50 === false ? 'Below ↓' : 'N/A',
            cls: stats.ratio_above_ma_50 === true ? 'stat-good' : stats.ratio_above_ma_50 === false ? 'stat-bad' : 'stat-neutral',
            tip: `50-day moving average of the price ratio. Above (green) = favors ${symbolA}. Below (red) = favors ${symbolB}.`,
        },
        {
            label: `Ratio vs 200d MA`,
            value: stats.ratio_above_ma_200 === true ? 'Above ↑' : stats.ratio_above_ma_200 === false ? 'Below ↓' : 'N/A',
            cls: stats.ratio_above_ma_200 === true ? 'stat-good' : stats.ratio_above_ma_200 === false ? 'stat-bad' : 'stat-neutral',
            tip: `200-day moving average of the price ratio. Above (green) = favors ${symbolA}. Below (red) = favors ${symbolB}.`,
        },
        {
            label: 'Momentum (ROC)',
            value: stats.momentum_roc !== null ? `${stats.momentum_roc > 0 ? '+' : ''}${fmt(stats.momentum_roc, 2)}%` : 'N/A',
            cls: stats.momentum_roc > 0 ? 'stat-good' : stats.momentum_roc < 0 ? 'stat-bad' : 'stat-neutral',
            tip: `Rate of Change over 20 days on the price ratio. Positive (green) = favors ${symbolA}. Negative (red) = favors ${symbolB}.`,
        },
        {
            label: 'Momentum Direction',
            value: stats.momentum_direction || 'N/A',
            cls: stats.momentum_direction === 'UP' ? 'stat-good' : stats.momentum_direction === 'DOWN' ? 'stat-bad' : 'stat-neutral',
            tip: `Slope of the ratio over 20 days. UP (green) = favors ${symbolA}. DOWN (red) = favors ${symbolB}. FLAT = neutral.`,
        },
        {
            label: retDiffLabel || 'Return Differential',
            value: retDiffVal !== null ? `${retDiffVal > 0 ? '+' : ''}${fmt(retDiffVal, 2)}%` : 'N/A',
            cls: retDiffVal !== null ? (retDiffVal > 0 ? 'stat-good' : retDiffVal < 0 ? 'stat-bad' : 'stat-neutral') : 'stat-neutral',
            tip: `Return difference: positive (green) = ${symbolA} outperformed. Negative (red) = ${symbolB} outperformed.`,
        },
        {
            label: 'Correlation',
            value: fmt(stats.correlation, 4),
            cls: 'stat-neutral',
            tip: 'Pearson correlation between the two price series. High (>0.7) = they move together, making relative analysis meaningful. Not directional — does not favor either ticker.',
        },
        {
            label: 'Ratio Z-Score',
            value: fmt(stats.current_zscore, 2),
            cls: 'stat-neutral',
            tip: 'How far the current ratio is from its 20-day mean, in standard deviations. Extreme values may suggest overextension but does not directly favor either ticker.',
        },
        {
            label: 'Hurst Exponent',
            value: fmt(stats.hurst_exponent, 4),
            cls: 'stat-neutral',
            tip: 'Measures trend persistence of the ratio. >0.5 = trending (outperformance tends to continue). <0.5 = mean-reverting. Context metric — does not directly favor either ticker.',
        },
        {
            label: 'ADF p-value (ratio)',
            value: fmt(stats.adf_pvalue, 4),
            cls: 'stat-neutral',
            tip: 'Augmented Dickey-Fuller test on the ratio. Low (<0.05) = mean-reverting. High (>0.05) = trend may persist. Context metric — does not directly favor either ticker.',
        },
    ];

    // Add return comparison rows for each period (no color — individual returns don't indicate relative outperformance)
    for (const p of retPeriods) {
        const rd = relRet[p];
        if (rd && rd.return_a !== null) {
            metrics.push({
                label: `${symbolA} Return (${p})`,
                value: `${rd.return_a > 0 ? '+' : ''}${fmt(rd.return_a, 1)}%`,
                cls: 'stat-neutral',
                tip: `Total return of ${symbolA} over ${p}. Compare with ${symbolB} to gauge relative performance.`,
            });
            metrics.push({
                label: `${symbolB} Return (${p})`,
                value: `${rd.return_b > 0 ? '+' : ''}${fmt(rd.return_b, 1)}%`,
                cls: 'stat-neutral',
                tip: `Total return of ${symbolB} over ${p}. Compare with ${symbolA} to gauge relative performance.`,
            });
        }
    }

    grid.innerHTML = metrics.map(m => `
        <div class="stat-card has-tooltip" data-tip="${escapeHtml(m.tip || '')}">
            <div class="stat-label">${m.label} <span class="stat-info">i</span></div>
            <div class="stat-value ${m.cls}">${m.value}</div>
        </div>
    `).join('');
}

// ── Technical Confirmation Badges ───────────────────────────────────────────

function renderTechSignals(confirmation) {
    const container = document.getElementById('tech-signals');
    if (!confirmation || !confirmation.signals) {
        container.innerHTML = '<span class="text-sm text-gray-500">No technical data</span>';
        return;
    }

    const dirCls = confirmation.direction === 'FAVORS_A' ? 'favors-a' :
                   confirmation.direction === 'FAVORS_B' ? 'favors-b' : 'neutral';

    const dirLabel = confirmation.direction === 'FAVORS_A' ? 'FAVORS A' :
                     confirmation.direction === 'FAVORS_B' ? 'FAVORS B' : 'NEUTRAL';

    let html = `<span class="tech-badge ${dirCls}"><strong>${dirLabel}</strong></span>`;

    confirmation.signals.forEach(sig => {
        const cls = sig.includes('positive') || sig.includes('strong') || sig.includes('bullish') || sig.includes('above upper') ? 'favors-a' :
                    sig.includes('negative') || sig.includes('weak') || sig.includes('bearish') || sig.includes('below lower') ? 'favors-b' : 'neutral';
        html += `<span class="tech-badge ${cls}">${sig}</span>`;
    });

    container.innerHTML = html;
}

// ── Signal Banner ───────────────────────────────────────────────────────────

function renderSignalBanner(signal, symbolA, symbolB) {
    const banner = document.getElementById('signal-banner');
    const icon   = document.getElementById('signal-icon');
    const dirEl  = document.getElementById('signal-direction');
    const detEl  = document.getElementById('signal-detail');

    const dir = signal.direction || 'NEUTRAL';
    const conviction = signal.conviction || 0;

    // Remove old classes
    banner.className = 'bg-surface-2 rounded-xl border border-gray-800 p-5';
    icon.className = 'w-14 h-14 rounded-xl flex items-center justify-center text-2xl font-bold';

    // Wording: ≥75% = STRONGLY FAVORS, 55-74% = FAVORS, <55% = NEUTRAL
    const prefix = conviction >= 75 ? 'STRONGLY FAVORS' : conviction >= 55 ? 'FAVORS' : '';

    if (prefix && dir === 'FAVOR_A') {
        banner.classList.add('signal-buy');
        icon.classList.add('signal-icon-buy');
        icon.textContent = 'A';
        dirEl.textContent = `${prefix} ${symbolA || 'A'}`;
        dirEl.style.color = COLORS.gain;
    } else if (prefix && dir === 'FAVOR_B') {
        banner.classList.add('signal-sell');
        icon.classList.add('signal-icon-sell');
        icon.textContent = 'B';
        dirEl.textContent = `${prefix} ${symbolB || 'B'}`;
        dirEl.style.color = COLORS.loss;
    } else {
        banner.classList.add('signal-none');
        icon.classList.add('signal-icon-none');
        icon.textContent = '=';
        dirEl.textContent = 'NEUTRAL';
        dirEl.style.color = COLORS.text;
    }

    detEl.textContent = signal.detail || '';

    // Conviction meter (0-100%)
    const fill = document.getElementById('conviction-fill');
    const label = document.getElementById('conviction-label');

    fill.style.width = `${conviction}%`;
    fill.className = 'conviction-meter-fill ' + getConvictionColorClass(conviction);
    label.textContent = `${conviction}%`;
    label.style.color = getConvictionColor(conviction);
}

function getConvictionColorClass(pct) {
    if (pct <= 20) return 'conviction-fill-vlow';
    if (pct <= 40) return 'conviction-fill-low';
    if (pct <= 60) return 'conviction-fill-mid';
    if (pct <= 80) return 'conviction-fill-high';
    return 'conviction-fill-vhigh';
}

function getConvictionColor(pct) {
    if (pct <= 20) return '#ef4444';
    if (pct <= 40) return '#f97316';
    if (pct <= 60) return '#eab308';
    if (pct <= 80) return '#84cc16';
    return '#22c55e';
}

// ── AI Recommendation ───────────────────────────────────────────────────────

function renderAIRecommendation(aiRec) {
    const recEl = document.getElementById('ai-recommendation');
    const risksEl = document.getElementById('ai-risks');
    const riskList = document.getElementById('ai-risk-list');

    recEl.textContent = aiRec.recommendation || 'No recommendation available.';

    if (aiRec.risk_factors && aiRec.risk_factors.length > 0) {
        risksEl.classList.remove('hidden');
        riskList.innerHTML = aiRec.risk_factors
            .map(r => `<li class="flex items-start gap-2"><span class="text-loss mt-0.5">&#9888;</span> ${escapeHtml(r)}</li>`)
            .join('');
    } else {
        risksEl.classList.add('hidden');
    }
}

// ── Chart Helpers ───────────────────────────────────────────────────────────

function baseChartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: {
                display: true,
                labels: { color: COLORS.text, font: { size: 10, family: FONT.family }, boxWidth: 12, padding: 12 },
            },
            tooltip: {
                backgroundColor: '#1c1f2e',
                titleColor: COLORS.white,
                bodyColor: COLORS.text,
                borderColor: '#252836',
                borderWidth: 1,
                titleFont: { family: FONT.family, size: 11 },
                bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
                padding: 10,
                cornerRadius: 6,
            },
        },
    };
}

function baseXScale(labels) {
    return {
        ticks: {
            color: COLORS.text,
            font: { size: 9, family: FONT.family },
            maxRotation: 0,
            callback: function(val, idx) {
                const label = this.getLabelForValue(val);
                return labels.includes(label) ? label : '';
            },
        },
        grid: { color: COLORS.grid, drawBorder: false },
    };
}

function baseYScale() {
    return {
        ticks: { color: COLORS.text, font: { size: 10, family: "'JetBrains Mono', monospace" } },
        grid: { color: COLORS.grid, drawBorder: false },
    };
}

function thinLabels(dates, count) {
    if (dates.length <= count) return dates;
    const step = Math.ceil(dates.length / count);
    return dates.filter((_, i) => i % step === 0);
}

function destroyChart(key) {
    if (charts[key]) {
        charts[key].destroy();
        delete charts[key];
    }
}

// ── Utilities ───────────────────────────────────────────────────────────────

function fmt(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return 'N/A';
    return Number(val).toFixed(decimals);
}

function hexToRgba(hex, alpha) {
    // Handle rgba() strings passed in
    if (hex.startsWith('rgba')) return hex;
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function escapeHtml(str) {
    return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function showError(msg) {
    const el = document.getElementById('error-msg');
    el.textContent = msg;
    el.classList.remove('hidden');
}

// ── Autocomplete / Ticker Search ────────────────────────────────────────────

let searchTimers = {};
let activeDropdown = null;
let activeIndex = -1;

function setupAutocomplete(inputId, dropdownId) {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);

    input.addEventListener('input', () => {
        const query = input.value.trim();
        clearTimeout(searchTimers[inputId]);

        if (query.length < 1) {
            hideDropdown(dropdownId);
            return;
        }

        searchTimers[inputId] = setTimeout(() => {
            fetchSearch(query, dropdownId, inputId);
        }, 250);
    });

    input.addEventListener('keydown', (e) => {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        if (!items.length || dropdown.classList.contains('hidden')) {
            if (e.key === 'Enter') analyzePair();
            return;
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIndex = Math.min(activeIndex + 1, items.length - 1);
            updateActiveItem(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIndex = Math.max(activeIndex - 1, 0);
            updateActiveItem(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (activeIndex >= 0 && items[activeIndex]) {
                selectItem(items[activeIndex], inputId, dropdownId);
            } else {
                hideDropdown(dropdownId);
                analyzePair();
            }
        } else if (e.key === 'Escape') {
            hideDropdown(dropdownId);
        }
    });

    input.addEventListener('blur', () => {
        setTimeout(() => hideDropdown(dropdownId), 200);
    });

    input.addEventListener('focus', () => {
        const query = input.value.trim();
        if (query.length >= 1) {
            clearTimeout(searchTimers[inputId]);
            searchTimers[inputId] = setTimeout(() => {
                fetchSearch(query, dropdownId, inputId);
            }, 150);
        }
    });
}

async function fetchSearch(query, dropdownId, inputId) {
    const dropdown = document.getElementById(dropdownId);

    dropdown.innerHTML = '<div class="autocomplete-loading">Searching...</div>';
    dropdown.classList.remove('hidden');
    activeDropdown = dropdownId;
    activeIndex = -1;

    try {
        const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await resp.json();
        const results = data.results || [];

        if (results.length === 0) {
            dropdown.innerHTML = '<div class="autocomplete-loading">No results found</div>';
            return;
        }

        dropdown.innerHTML = results.map((r, i) => `
            <div class="autocomplete-item" data-symbol="${escapeHtml(r.symbol)}"
                 onmousedown="selectItem(this, '${inputId}', '${dropdownId}')">
                <span class="ac-symbol">${escapeHtml(r.symbol)}</span>
                <span class="ac-name">${escapeHtml(r.name)}</span>
                <span class="ac-meta">${escapeHtml(r.exchange || r.type || '')}</span>
            </div>
        `).join('');
    } catch (err) {
        dropdown.innerHTML = '<div class="autocomplete-loading">Search failed</div>';
    }
}

function selectItem(el, inputId, dropdownId) {
    const symbol = el.getAttribute('data-symbol');
    document.getElementById(inputId).value = symbol;
    hideDropdown(dropdownId);
}

function hideDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    dropdown.classList.add('hidden');
    activeIndex = -1;
    if (activeDropdown === dropdownId) activeDropdown = null;
}

function updateActiveItem(items) {
    items.forEach((item, i) => {
        item.classList.toggle('active', i === activeIndex);
    });
    if (activeIndex >= 0 && items[activeIndex]) {
        items[activeIndex].scrollIntoView({ block: 'nearest' });
    }
}

document.addEventListener('click', (e) => {
    if (activeDropdown && !e.target.closest('.relative')) {
        hideDropdown(activeDropdown);
    }
});

// ── Analysis History (localStorage) ─────────────────────────────────────────

const HISTORY_KEY = 'whichticker_history';
const HISTORY_MAX = 10;

function getHistory() {
    try {
        return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    } catch { return []; }
}

function saveHistory(history) {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}

function addToHistory(tickerA, tickerB, period, signal, conviction) {
    const history = getHistory();

    const idx = history.findIndex(h => h.tickerA === tickerA && h.tickerB === tickerB && h.period === period);
    if (idx !== -1) history.splice(idx, 1);

    history.unshift({
        tickerA,
        tickerB,
        period,
        signal,
        conviction,
        date: new Date().toISOString(),
    });

    if (history.length > HISTORY_MAX) history.length = HISTORY_MAX;

    saveHistory(history);
    renderHistory();
}

function removeFromHistory(index) {
    const history = getHistory();
    history.splice(index, 1);
    saveHistory(history);
    renderHistory();
}

function renderHistory() {
    const history = getHistory();
    const list = document.getElementById('history-list');
    const countEl = document.getElementById('history-count');

    if (history.length === 0) {
        countEl.textContent = '';
        list.innerHTML = '<div class="px-5 py-4 text-center text-xs text-gray-600">No analyses yet — enter a pair above to get started.</div>';
        return;
    }

    countEl.textContent = `(${history.length})`;

    list.innerHTML = history.map((h, i) => {
        const sigDir = (h.signal || 'NEUTRAL').toUpperCase();
        const conv = h.conviction || 0;
        // Handle legacy 1-5 scale from old history entries (new scale is 0-100)
        const convPct = (conv > 0 && conv <= 5) ? conv * 20 : conv;

        // Wording: ≥75% = STRONGLY FAVORS, 55-74% = FAVORS, <55% = NEUTRAL
        const histPrefix = convPct >= 75 ? 'STRONGLY FAVORS' : convPct >= 55 ? 'FAVORS' : '';
        const isFavor = (sigDir === 'FAVOR_A' || sigDir === 'BUY' || sigDir === 'FAVOR_B' || sigDir === 'SELL');
        const isA = sigDir === 'FAVOR_A' || sigDir === 'BUY';

        let sigCls, sigLabel;
        if (histPrefix && isFavor) {
            sigCls = isA ? 'favor-a' : 'favor-b';
            sigLabel = `${histPrefix} ${isA ? h.tickerA : h.tickerB}`;
        } else {
            sigCls = 'none';
            sigLabel = 'NEUTRAL';
        }

        const meterFill = `<div class="mini-meter"><div class="mini-meter-fill ${getConvictionColorClass(convPct)}" style="width:${convPct}%"></div></div>`;
        const meterLabel = `<span class="mini-label">${convPct}%</span>`;

        const d = new Date(h.date);
        const dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
                        ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

        return `
            <div class="history-row" onclick="replayHistory(${i})">
                <span class="history-pair">${escapeHtml(h.tickerA)} / ${escapeHtml(h.tickerB)}</span>
                <span class="history-period">${escapeHtml(h.period)}</span>
                <span class="history-signal ${sigCls}">${sigLabel}</span>
                <div class="history-conviction">${meterFill}${meterLabel}</div>
                <span class="history-date">${dateStr}</span>
                <button class="history-delete" onclick="event.stopPropagation(); removeFromHistory(${i})" title="Remove">
                    <i data-lucide="x" class="w-3 h-3"></i>
                </button>
            </div>
        `;
    }).join('');

    lucide.createIcons();
}

function replayHistory(index) {
    const history = getHistory();
    const h = history[index];
    if (!h) return;

    document.getElementById('input-ticker-a').value = h.tickerA;
    document.getElementById('input-ticker-b').value = h.tickerB;
    document.getElementById('input-period').value = h.period;

    analyzePair();
}

let historyExpanded = true;

function toggleHistoryPanel() {
    const list = document.getElementById('history-list');
    const chevron = document.getElementById('history-chevron');
    historyExpanded = !historyExpanded;

    if (historyExpanded) {
        list.classList.remove('hidden');
        chevron.classList.add('expanded');
    } else {
        list.classList.add('hidden');
        chevron.classList.remove('expanded');
    }
}

// ── Event Listeners ─────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
    setupAutocomplete('input-ticker-a', 'dropdown-a');
    setupAutocomplete('input-ticker-b', 'dropdown-b');
    renderHistory();
});
