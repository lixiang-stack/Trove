(() => {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/", updateViaCache: "none" })
      .then((registration) => registration.update().catch(() => {}))
      .catch(() => {
        // Installation is optional; the normal browser experience remains.
      });
  });
})();
