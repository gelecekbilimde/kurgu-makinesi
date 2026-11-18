/* Starter "calm" motion, driven by hf-kit (kit.onFrame). Timings and easings come from tokens.css.
 *   calm.entry(els)         fade + small rise, one after another
 *   calm.highlight(el)      marker sweep left to right
 *   calm.draw(path)         stroke draws itself
 *   calm.hand(el)           handwritten note revealed left to right (never clips the last glyph)
 *   calm.exit(el)           quick fade at the very end
 *   calm.start()            register everything with kit.onFrame
 */
(function () {
  "use strict";
  const parts = [];
  const n = (name) => kit.tokenNum(name);
  const ease = (name) => kit.token(name);

  function entry(els) {
    Array.from(els).forEach((el, i) => parts.push((t) => {
      const p = kit.progress(t, n("--motion-delay") + i * n("--motion-stagger"), n("--motion-in"), ease("--motion-ease"));
      el.style.opacity = String(p);
      el.style.translate = "0 " + ((1 - p) * n("--motion-rise")) + "cqw";
    }));
  }
  function highlight(el) {
    parts.push((t) => {
      const p = kit.progress(t, n("--motion-hl-at"), n("--motion-hl"), ease("--motion-hl-ease"));
      el.style.backgroundSize = (p * 100) + "% 38%";
    });
  }
  function draw(shape) {
    parts.push((t) => kit.draw(shape, kit.progress(t, n("--motion-draw-at"), n("--motion-draw"), ease("--motion-hl-ease"))));
  }
  function hand(el) {
    parts.push((t) => kit.reveal(el, kit.progress(t, n("--motion-hand-at"), n("--motion-hand"), ease("--motion-hl-ease"))));
  }
  function exit(el) {
    parts.push((t) => {
      const out = n("--motion-out");
      el.style.opacity = String(1 - kit.progress(t, kit.duration() - out - 1 / kit.fps(), out, "linear"));
    });
  }
  function start() {
    kit.onFrame((t) => parts.forEach((f) => f(t)));
  }
  window.calm = { entry, highlight, draw, hand, exit, start };
})();
