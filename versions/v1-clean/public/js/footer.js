// CHANGE-06 / CHANGE-09: updated footer tagline plus a live clock (dynamic
// content that changes every second and differs on every page load).
function startFooterClock() {
  const el = document.getElementById('footer-clock');
  if (!el) return;
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString();
  };
  tick();
  setInterval(tick, 1000);
}

document.addEventListener('DOMContentLoaded', startFooterClock);
