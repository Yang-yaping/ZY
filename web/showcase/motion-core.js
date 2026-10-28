/* Small shared input policy; no browser dependency so momentum is testable. */
(function (root) {
  'use strict';
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
  function wheelPixels(event, viewportHeight = 800) {
    const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewportHeight : 1;
    return { x: event.deltaX * multiplier, y: event.deltaY * multiplier };
  }
  class WheelIntent {
    constructor(threshold = 48, quietMs = 180) {
      this.threshold = threshold;
      this.quietMs = quietMs;
      this.lastAt = -Infinity;
      this.total = 0;
      this.used = false;
    }
    observe(delta, now, blocked = false) {
      if (now - this.lastAt > this.quietMs) { this.total = 0; this.used = false; }
      this.lastAt = now;
      if (blocked) { this.used = true; this.total = 0; return 0; }
      if (this.used) return 0;
      if (Math.sign(delta) !== Math.sign(this.total)) this.total = 0;
      this.total += delta;
      if (Math.abs(this.total) < this.threshold) return 0;
      const direction = Math.sign(this.total);
      this.used = true;
      this.total = 0;
      return direction;
    }
  }
  const api = { clamp, wheelPixels, WheelIntent };
  root.YinbiMotion = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
