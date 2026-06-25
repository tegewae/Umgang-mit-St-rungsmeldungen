/**
 * Minimal chart renderer – Canvas API, no dependencies.
 * Supports: barChart(), hBarChart(), donutChart()
 */
(function(global) {
  'use strict';

  const PAL = {
    blue:   '#5B9BD5',
    navy:   '#2E5277',
    amber:  '#D4911A',
    green:  '#2E6644',
    rule:   '#D1DCE8',
    text:   '#778899',
    textDk: '#1B2A3B',
  };

  function px(n) { return Math.round(n); }

  function textEllipsis(ctx, text, maxW) {
    if (ctx.measureText(text).width <= maxW) return text;
    while (text.length > 1 && ctx.measureText(text + '…').width > maxW) {
      text = text.slice(0, -1);
    }
    return text + '…';
  }

  // Vertical bar chart
  global.barChart = function(canvasId, labels, data, opts) {
    opts = opts || {};
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const dpr    = window.devicePixelRatio || 1;
    const W      = canvas.offsetWidth  || 640;
    const H      = canvas.offsetHeight || 200;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width  = W + 'px';
    canvas.style.height = H + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const PAD = { top: 16, right: 16, bottom: 40, left: 36 };
    const chartW = W - PAD.left - PAD.right;
    const chartH = H - PAD.top  - PAD.bottom;

    const maxVal = Math.max(...data, 1);
    const yTicks = Math.min(maxVal, 8);

    // Grid lines
    ctx.strokeStyle = PAL.rule;
    ctx.lineWidth   = 1;
    for (let i = 0; i <= yTicks; i++) {
      const y = px(PAD.top + chartH - (i / yTicks) * chartH) + .5;
      ctx.beginPath();
      ctx.moveTo(PAD.left, y);
      ctx.lineTo(PAD.left + chartW, y);
      ctx.stroke();
      // Y label
      ctx.fillStyle   = PAL.text;
      ctx.font        = `11px 'Segoe UI',system-ui,sans-serif`;
      ctx.textAlign   = 'right';
      ctx.textBaseline = 'middle';
      const val = Math.round((i / yTicks) * maxVal);
      ctx.fillText(val, PAD.left - 6, y);
    }

    // Bars
    const barW   = chartW / labels.length;
    const barGap = barW * 0.25;
    for (let i = 0; i < labels.length; i++) {
      const x   = PAD.left + i * barW + barGap / 2;
      const bW  = barW - barGap;
      const bH  = data[i] / maxVal * chartH;
      const y   = PAD.top + chartH - bH;

      // Rounded top corners
      const r = Math.min(3, bH / 2);
      ctx.fillStyle = opts.color || PAL.blue;
      ctx.beginPath();
      ctx.moveTo(px(x + r), px(y));
      ctx.lineTo(px(x + bW - r), px(y));
      ctx.quadraticCurveTo(px(x + bW), px(y), px(x + bW), px(y + r));
      ctx.lineTo(px(x + bW), px(y + bH));
      ctx.lineTo(px(x), px(y + bH));
      ctx.lineTo(px(x), px(y + r));
      ctx.quadraticCurveTo(px(x), px(y), px(x + r), px(y));
      ctx.closePath();
      ctx.fill();

      // Value label on bar
      if (data[i] > 0) {
        ctx.fillStyle    = '#fff';
        ctx.font         = `bold 11px 'Segoe UI',system-ui,sans-serif`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'bottom';
        if (bH > 18) ctx.fillText(data[i], px(x + bW / 2), px(y + bH) - 3);
      }

      // X label
      ctx.fillStyle    = PAL.text;
      ctx.font         = `11px 'Segoe UI',system-ui,sans-serif`;
      ctx.textAlign    = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(labels[i], px(x + bW / 2), PAD.top + chartH + 8);
    }
  };

  // Horizontal bar chart
  global.hBarChart = function(canvasId, labels, data, opts) {
    opts = opts || {};
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W   = canvas.offsetWidth  || 400;
    const H   = canvas.offsetHeight || 240;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width  = W + 'px';
    canvas.style.height = H + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const LABEL_W = 130;
    const PAD     = { top: 8, right: 40, bottom: 8, left: LABEL_W };
    const chartW  = W - PAD.left - PAD.right;
    const chartH  = H - PAD.top  - PAD.bottom;

    const maxVal = Math.max(...data, 1);
    const rowH   = chartH / labels.length;
    const barGap = rowH * 0.3;

    for (let i = 0; i < labels.length; i++) {
      const y  = PAD.top + i * rowH + barGap / 2;
      const bH = rowH - barGap;
      const bW = (data[i] / maxVal) * chartW;

      ctx.fillStyle = opts.color || PAL.navy;
      const r = Math.min(3, bH / 2);
      ctx.beginPath();
      ctx.moveTo(PAD.left, px(y + r));
      ctx.lineTo(PAD.left, px(y + bH - r));
      ctx.quadraticCurveTo(PAD.left, px(y + bH), PAD.left + r, px(y + bH));
      ctx.lineTo(PAD.left + bW - r, px(y + bH));
      ctx.quadraticCurveTo(PAD.left + bW, px(y + bH), PAD.left + bW, px(y + bH - r));
      ctx.lineTo(PAD.left + bW, px(y + r));
      ctx.quadraticCurveTo(PAD.left + bW, px(y), PAD.left + bW - r, px(y));
      ctx.lineTo(PAD.left + r, px(y));
      ctx.quadraticCurveTo(PAD.left, px(y), PAD.left, px(y + r));
      ctx.closePath();
      ctx.fill();

      // Label
      ctx.fillStyle    = PAL.textDk;
      ctx.font         = `12px 'Segoe UI',system-ui,sans-serif`;
      ctx.textAlign    = 'right';
      ctx.textBaseline = 'middle';
      const label = textEllipsis(ctx, labels[i], LABEL_W - 10);
      ctx.fillText(label, PAD.left - 8, px(y + bH / 2));

      // Value
      ctx.fillStyle    = PAL.text;
      ctx.font         = `bold 11px 'Segoe UI',system-ui,sans-serif`;
      ctx.textAlign    = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(data[i], PAD.left + bW + 6, px(y + bH / 2));
    }
  };

  // Donut chart
  global.donutChart = function(canvasId, labels, data, colors) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W   = canvas.offsetWidth  || 300;
    const H   = canvas.offsetHeight || 240;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width  = W + 'px';
    canvas.style.height = H + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const total = data.reduce((a, b) => a + b, 0);
    if (!total) {
      ctx.fillStyle    = PAL.text;
      ctx.font         = `13px 'Segoe UI',system-ui,sans-serif`;
      ctx.textAlign    = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('Keine Daten', W / 2, H / 2);
      return;
    }

    const LEG_H  = 28 * labels.length;
    const cx     = W / 2;
    const cy     = (H - LEG_H) / 2;
    const radius = Math.min(cx, cy) * 0.85;
    const inner  = radius * 0.62;

    let angle = -Math.PI / 2;
    for (let i = 0; i < data.length; i++) {
      const slice = (data[i] / total) * 2 * Math.PI;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, angle, angle + slice);
      ctx.closePath();
      ctx.fillStyle = (colors && colors[i]) || [PAL.blue, PAL.navy, PAL.amber, PAL.green][i % 4];
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth   = 2;
      ctx.stroke();
      angle += slice;
    }

    // Donut hole
    ctx.beginPath();
    ctx.arc(cx, cy, inner, 0, 2 * Math.PI);
    ctx.fillStyle = '#fff';
    ctx.fill();

    // Center total
    ctx.fillStyle    = PAL.textDk;
    ctx.font         = `bold 22px 'Segoe UI',system-ui,sans-serif`;
    ctx.textAlign    = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total, cx, cy - 6);
    ctx.fillStyle = PAL.text;
    ctx.font      = `11px 'Segoe UI',system-ui,sans-serif`;
    ctx.fillText('Gesamt', cx, cy + 14);

    // Legend
    const legTop = H - LEG_H + 4;
    for (let i = 0; i < labels.length; i++) {
      const y    = legTop + i * 28;
      const col  = (colors && colors[i]) || [PAL.blue, PAL.navy, PAL.amber, PAL.green][i % 4];
      const pct  = total ? Math.round(data[i] / total * 100) : 0;

      ctx.fillStyle   = col;
      ctx.fillRect(px(cx - 70), px(y + 6), 12, 12);

      ctx.fillStyle    = PAL.textDk;
      ctx.font         = `12px 'Segoe UI',system-ui,sans-serif`;
      ctx.textAlign    = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(labels[i], px(cx - 54), px(y + 12));

      ctx.fillStyle  = PAL.text;
      ctx.font       = `bold 12px 'Segoe UI',system-ui,sans-serif`;
      ctx.textAlign  = 'right';
      ctx.fillText(`${data[i]} (${pct}%)`, px(cx + 70), px(y + 12));
    }
  };

})(window);
