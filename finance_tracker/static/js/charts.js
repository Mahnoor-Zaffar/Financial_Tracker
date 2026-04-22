function readChartPayload(nodeId) {
  const node = document.getElementById(nodeId);
  if (!node) return null;
  const payload = node.getAttribute("data-chart-payload");
  if (!payload) return null;
  try {
    return JSON.parse(payload);
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
    ink: cssVar("--ink", "#1c222b"),
    inkSoft: cssVar("--ink-soft", "#4f5a6c"),
    line: cssVar("--line", "#dde2e9"),
    brand: cssVar("--brand", "#1f5d6e"),
    positive: cssVar("--positive", "#2f6f52"),
    danger: cssVar("--danger", "#a14c44"),
    warning: cssVar("--warning", "#9b6a2d"),
    surface: cssVar("--surface", "#ffffff"),
  };
}

function toNums(values) {
  return Array.isArray(values) ? values.map((value) => Number(value || 0)) : [];
}

function hasMeaningfulData(series) {
  return series.some((value) => value > 0);
}

function prepareCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const displayWidth = canvas.clientWidth || canvas.width || 320;
  const displayHeight = Number(canvas.getAttribute("height")) || canvas.clientHeight || 180;
  canvas.width = Math.round(displayWidth * ratio);
  canvas.height = Math.round(displayHeight * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width: displayWidth, height: displayHeight };
}

function drawCenteredMessage(ctx, width, height, message, colors) {
  ctx.save();
  ctx.fillStyle = colors.inkSoft;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = '600 13px "Avenir Next", "Segoe UI", sans-serif';
  ctx.fillText(message, width / 2, height / 2);
  ctx.restore();
}

function drawLegend(ctx, items, width, top, colors) {
  const radius = 5;
  const gap = 16;
  ctx.save();
  ctx.font = '600 12px "Avenir Next", "Segoe UI", sans-serif';
  ctx.textBaseline = "middle";
  let x = 0;
  items.forEach(({ label, color }, index) => {
    const labelWidth = ctx.measureText(label).width;
    x += index === 0 ? 0 : gap;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x + radius, top, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = colors.inkSoft;
    ctx.fillText(label, x + radius * 2 + 6, top);
    x += radius * 2 + 6 + labelWidth;
  });
  ctx.restore();
}

function drawFlowChart() {
  const canvas = document.getElementById("flowChart");
  const payload = readChartPayload("flowChart");
  if (!canvas || !payload) return;

  const colors = palette();
  const income = toNums(payload.income);
  const expense = toNums(payload.expense);
  const labels = payload.labels || [];
  const hasData = hasMeaningfulData([...income, ...expense]);
  const { ctx, width, height } = prepareCanvas(canvas);

  ctx.clearRect(0, 0, width, height);
  if (!hasData) {
    drawCenteredMessage(ctx, width, height, "No trend data yet. Add income or expense transactions.", colors);
    return;
  }

  const margin = { top: 18, right: 12, bottom: 40, left: 40 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const maxValue = Math.max(...income, ...expense, 1);
  const ticks = 4;

  ctx.save();
  ctx.strokeStyle = rgba(colors.line, 0.8);
  ctx.lineWidth = 1;
  for (let index = 0; index <= ticks; index += 1) {
    const y = margin.top + (chartHeight / ticks) * index;
    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(width - margin.right, y);
    ctx.stroke();
  }

  ctx.fillStyle = colors.inkSoft;
  ctx.font = '500 11px "Avenir Next", "Segoe UI", sans-serif';
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let index = 0; index <= ticks; index += 1) {
    const value = Math.round(maxValue - (maxValue / ticks) * index);
    const y = margin.top + (chartHeight / ticks) * index;
    ctx.fillText(String(value), margin.left - 6, y);
  }

  const stepX = labels.length > 1 ? chartWidth / (labels.length - 1) : chartWidth / 2;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  labels.forEach((label, index) => {
    const x = labels.length > 1 ? margin.left + stepX * index : margin.left + chartWidth / 2;
    ctx.fillText(label, x, height - margin.bottom + 10);
  });

  function drawSeries(points, strokeColor, fillColor) {
    ctx.beginPath();
    points.forEach((value, index) => {
      const x = labels.length > 1 ? margin.left + stepX * index : margin.left + chartWidth / 2;
      const y = margin.top + chartHeight - (value / maxValue) * chartHeight;
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 2.2;
    ctx.stroke();

    ctx.lineTo(margin.left + chartWidth, margin.top + chartHeight);
    ctx.lineTo(margin.left, margin.top + chartHeight);
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();

    points.forEach((value, index) => {
      const x = labels.length > 1 ? margin.left + stepX * index : margin.left + chartWidth / 2;
      const y = margin.top + chartHeight - (value / maxValue) * chartHeight;
      ctx.beginPath();
      ctx.fillStyle = strokeColor;
      ctx.arc(x, y, 2.8, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  drawSeries(income, colors.positive, rgba(colors.positive, 0.14));
  drawSeries(expense, colors.danger, rgba(colors.danger, 0.12));
  drawLegend(
    ctx,
    [
      { label: "Income", color: colors.positive },
      { label: "Expense", color: colors.danger },
    ],
    width,
    height - 14,
    colors
  );
  ctx.restore();
}

function drawCategoryChart() {
  const canvas = document.getElementById("categoryChart");
  const payload = readChartPayload("categoryChart");
  if (!canvas || !payload) return;

  const colors = palette();
  const values = toNums(payload.values);
  const labels = payload.labels || [];
  const hasData = hasMeaningfulData(values);
  const { ctx, width, height } = prepareCanvas(canvas);

  ctx.clearRect(0, 0, width, height);
  if (!hasData) {
    drawCenteredMessage(ctx, width, height, "No category spend data available.", colors);
    return;
  }

  const paletteColors = [
    rgba(colors.brand, 0.88),
    rgba(colors.positive, 0.9),
    rgba(colors.warning, 0.88),
    rgba(colors.danger, 0.84),
    rgba(cssVar("--line-strong", "#8a98ab"), 0.92),
    rgba("#3b7f9a", 0.84),
    rgba("#6f835f", 0.82),
    rgba("#887052", 0.86),
  ];
  const total = values.reduce((sum, value) => sum + value, 0) || 1;
  const radius = Math.min(width, height) * 0.28;
  const innerRadius = radius * 0.62;
  const centerX = width / 2;
  const centerY = height / 2 - 8;
  let start = -Math.PI / 2;

  values.forEach((value, index) => {
    const slice = (value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.arc(centerX, centerY, radius, start, start + slice);
    ctx.closePath();
    ctx.fillStyle = paletteColors[index % paletteColors.length];
    ctx.fill();
    start += slice;
  });

  ctx.beginPath();
  ctx.fillStyle = colors.surface;
  ctx.arc(centerX, centerY, innerRadius, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = colors.ink;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = '600 14px "Avenir Next", "Segoe UI", sans-serif';
  ctx.fillText("Spend", centerX, centerY);

  const legendItems = labels.slice(0, values.length).map((label, index) => ({
    label,
    color: paletteColors[index % paletteColors.length],
  }));
  drawLegend(ctx, legendItems, width, height - 12, colors);
}

function mountCharts() {
  drawFlowChart();
  drawCategoryChart();
}

document.addEventListener("DOMContentLoaded", mountCharts);
window.addEventListener("fintrack:theme-change", mountCharts);
