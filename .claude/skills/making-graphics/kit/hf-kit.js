/* hf-kit: mechanics for making-graphics templates. No looks live here: colours, fonts, sizes, durations and
 * easing choices come from the design's tokens (CSS custom properties), read with kit.token().
 *
 * Time: HyperFrames seeks every frame on its own and fires `hf-seek` with e.detail.time (seconds). Motion must be
 * a pure function of that time, so templates register a draw function with kit.onFrame(fn) and never use the
 * clock, timers or requestAnimationFrame.
 */
(function () {
  "use strict";
  const root = () => document.querySelector("[data-composition-id]");

  const EASE = {
    "linear": (x) => x,
    "out-cubic": (x) => 1 - Math.pow(1 - x, 3),
    "out-quint": (x) => 1 - Math.pow(1 - x, 5),
    "in-out-cubic": (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
    "in-out-sine": (x) => -(Math.cos(Math.PI * x) - 1) / 2,
  };

  function types() {
    const el = document.getElementById("kit-types");
    return el ? JSON.parse(el.textContent) : {};
  }

  function vars() {
    const raw = (window.__hyperframes && window.__hyperframes.getVariables) ? window.__hyperframes.getVariables() : {};
    const t = types();
    const out = {};
    for (const k of Object.keys(raw)) {
      const v = raw[k];
      if ((t[k] === "list" || t[k] === "number") && typeof v === "string") {
        out[k] = v === "" ? (t[k] === "list" ? [] : null) : JSON.parse(v);
      } else {
        out[k] = v;
      }
    }
    return out;
  }

  const duration = () => parseFloat(root().getAttribute("data-duration"));
  const fps = () => parseFloat(root().getAttribute("data-fps") || "25");

  function clamp01(x) { return Math.max(0, Math.min(1, x)); }

  function ease(name) {
    const f = EASE[(name || "linear").trim()];
    if (!f) throw new Error("hf-kit: unknown easing '" + name + "' (known: " + Object.keys(EASE).join(", ") + ")");
    return f;
  }

  function progress(t, start, dur, easeName) {
    if (dur <= 0) return t >= start ? 1 : 0;
    return ease(easeName)(clamp01((t - start) / dur));
  }

  function token(name, el) {
    return getComputedStyle(el || document.documentElement).getPropertyValue(name).trim();
  }

  function tokenNum(name, el) {
    const v = parseFloat(token(name, el));
    return Number.isFinite(v) ? v : 0;
  }

  /* Left-to-right reveal that never clips an overhanging last glyph (script fonts overhang their box): the
   * clip box extends past the element on every side, and at p=1 the right inset is negative. */
  function reveal(el, p) {
    const right = (1 - clamp01(p)) * 125 - 25;
    el.style.clipPath = "inset(-40% " + right + "% -40% -10%)";
  }

  /* Stroke draw-on for an SVG path/line/circle. */
  function draw(shape, p) {
    const len = shape.getTotalLength();
    shape.style.strokeDasharray = len + " " + len;
    shape.style.strokeDashoffset = String(len * (1 - clamp01(p)));
  }

  /* Shrink text to fit a width (never grow past the CSS size). */
  function fit(el, maxWidthPx) {
    const cs = getComputedStyle(el);
    const size = parseFloat(cs.fontSize);
    if (!(window.__hyperframes && window.__hyperframes.fitTextFontSize)) {
      el.style.fontSize = size * Math.min(1, maxWidthPx / Math.max(1, el.scrollWidth)) + "px";
      return;
    }
    const r = window.__hyperframes.fitTextFontSize(el.textContent, {
      fontFamily: cs.fontFamily, fontWeight: cs.fontWeight, maxWidth: maxWidthPx,
    });
    el.style.fontSize = Math.min(size, r.fontSize) + "px";
  }

  const frameFns = [];
  function onFrame(fn) {
    frameFns.push(fn);
    fn(0);
  }
  window.addEventListener("hf-seek", (e) => {
    const t = e && e.detail ? e.detail.time : 0;
    for (const fn of frameFns) fn(t);
  });

  window.kit = { vars, duration, fps, onFrame, progress, ease, token, tokenNum, reveal, draw, fit, clamp01 };
})();
