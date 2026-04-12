function readJsonNode(nodeId) {
  const node = document.getElementById(nodeId);
  if (!node) return null;
  try {
    return JSON.parse(node.textContent);
  } catch (_error) {
    return null;
  }
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function rgba(hex, alpha = 1) {
  const clean = hex.replace("#", "").trim();
  if (clean.length !== 6) return `rgba(39, 56, 76, ${alpha})`;
  const r = Number.parseInt(clean.slice(0, 2), 16);
  const g = Number.parseInt(clean.slice(2, 4), 16);
  const b = Number.parseInt(clean.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function palette() {
  return {
    inkSoft: cssVar("--ink-soft", "#4f5a6c"),
    line: cssVar("--line", "#dde2e9"),
    brand: cssVar("--brand", "#1f5d6e"),
    positive: cssVar("--positive", "#2f6f52"),
    danger: cssVar("--danger", "#a14c44"),
    warning: cssVar("--warning", "#9b6a2d"),
  };
}

function toNums(values) {
  return Array.isArray(values) ? values.map((value) => Number(value || 0)) : [];
}

function hasMeaningfulData(series) {
  return series.some((value) => value > 0);
}

let flowChart = null;
let categoryChart = null;

function buildFlowChart() {
  const canvas = document.getElementById("flowChart");
  const payload = readJsonNode("flow-chart-data");
  if (!canvas || !payload || typeof Chart === "undefined") return;

  const colors = palette();
  const income = toNums(payload.income);
  const expense = toNums(payload.expense);
  const hasData = hasMeaningfulData([...income, ...expense]);

  flowChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: payload.labels || [],
      datasets: [
        {
          label: "Income",
          data: income,
          borderColor: colors.positive,
          backgroundColor: rgba(colors.positive, 0.15),
          pointRadius: 2.6,
          pointHoverRadius: 4.2,
          borderWidth: 2.2,
          fill: true,
          tension: 0.34,
        },
        {
          label: "Expense",
          data: expense,
          borderColor: colors.danger,
          backgroundColor: rgba(colors.danger, 0.13),
          pointRadius: 2.6,
          pointHoverRadius: 4.2,
          borderWidth: 2.2,
          fill: true,
          tension: 0.34,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: colors.inkSoft,
            boxWidth: 12,
            boxHeight: 12,
            usePointStyle: true,
            pointStyle: "circle",
          },
        },
        tooltip: {
          backgroundColor: rgba(colors.brand, 0.92),
          titleColor: "#ffffff",
          bodyColor: "#ffffff",
          displayColors: false,
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { color: colors.inkSoft },
          grid: { color: rgba(colors.line, 0.75) },
        },
        x: {
          ticks: { color: colors.inkSoft },
          grid: { display: false },
        },
      },
    },
    plugins: [
      {
        id: "emptyFlowState",
        afterDraw(chart) {
          if (hasData) return;
          const { ctx, chartArea } = chart;
          if (!chartArea) return;
          ctx.save();
          ctx.fillStyle = colors.inkSoft;
          ctx.textAlign = "center";
          ctx.font = "600 13px Manrope, sans-serif";
          ctx.fillText(
            "No trend data yet. Add income or expense transactions.",
            (chartArea.left + chartArea.right) / 2,
            (chartArea.top + chartArea.bottom) / 2
          );
          ctx.restore();
        },
      },
    ],
  });
}

function buildCategoryChart() {
  const canvas = document.getElementById("categoryChart");
  const payload = readJsonNode("category-chart-data");
  if (!canvas || !payload || typeof Chart === "undefined") return;

  const colors = palette();
  const values = toNums(payload.values);
  const hasData = hasMeaningfulData(values);

  categoryChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: payload.labels || [],
      datasets: [
        {
          data: values,
          backgroundColor: [
            rgba(colors.brand, 0.88),
            rgba(colors.positive, 0.9),
            rgba(colors.warning, 0.88),
            rgba(colors.danger, 0.84),
            rgba(cssVar("--line-strong", "#8a98ab"), 0.92),
            rgba("#3b7f9a", 0.84),
            rgba("#6f835f", 0.82),
            rgba("#887052", 0.86),
          ],
          borderColor: cssVar("--surface", "#ffffff"),
          borderWidth: 2.2,
          hoverOffset: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "64%",
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: colors.inkSoft,
            boxWidth: 12,
            boxHeight: 12,
            usePointStyle: true,
            pointStyle: "circle",
          },
        },
        tooltip: {
          backgroundColor: rgba(colors.brand, 0.92),
          titleColor: "#ffffff",
          bodyColor: "#ffffff",
          displayColors: false,
        },
      },
    },
    plugins: [
      {
        id: "emptyCategoryState",
        afterDraw(chart) {
          if (hasData) return;
          const { ctx, chartArea } = chart;
          if (!chartArea) return;
          ctx.save();
          ctx.fillStyle = colors.inkSoft;
          ctx.textAlign = "center";
          ctx.font = "600 13px Manrope, sans-serif";
          ctx.fillText(
            "No category spend data available.",
            (chartArea.left + chartArea.right) / 2,
            (chartArea.top + chartArea.bottom) / 2
          );
          ctx.restore();
        },
      },
    ],
  });
}

function mountCharts() {
  buildFlowChart();
  buildCategoryChart();
}

function destroyCharts() {
  if (flowChart) {
    flowChart.destroy();
    flowChart = null;
  }
  if (categoryChart) {
    categoryChart.destroy();
    categoryChart = null;
  }
}

document.addEventListener("DOMContentLoaded", mountCharts);
window.addEventListener("fintrack:theme-change", () => {
  if (typeof Chart === "undefined") return;
  destroyCharts();
  mountCharts();
});
