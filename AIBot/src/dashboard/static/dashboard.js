/* CryptoBot Dashboard - Chart.js helpers */

const chartDefaults = {
    responsive: true,
    maintainAspectRatio: true,
    scales: {
        x: {
            ticks: { color: '#a0a0b0', maxRotation: 45, maxTicksLimit: 15 },
            grid: { color: 'rgba(255,255,255,0.05)' },
        },
        y: {
            ticks: { color: '#a0a0b0' },
            grid: { color: 'rgba(255,255,255,0.05)' },
        }
    },
    plugins: {
        legend: { labels: { color: '#e0e0e0' } },
        tooltip: {
            backgroundColor: '#16213e',
            titleColor: '#e0e0e0',
            bodyColor: '#a0a0b0',
            borderColor: '#2a2a4a',
            borderWidth: 1,
        }
    }
};

function createLineChart(canvasId, labels, data, label, color) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                borderColor: color || '#00d4aa',
                backgroundColor: (color || '#00d4aa') + '20',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHitRadius: 10,
            }]
        },
        options: chartDefaults
    });
}

function createBarChart(canvasId, labels, data, label) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const colors = data.map(v => v >= 0 ? '#00d4aa' : '#ff4757');

    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                backgroundColor: colors,
                borderRadius: 4,
            }]
        },
        options: {
            ...chartDefaults,
            plugins: { ...chartDefaults.plugins, legend: { display: false } }
        }
    });
}
