(() => {
  const body = document.body;
  if (!body || body.dataset.roxyKeyboardUx === "1") return;
  body.dataset.roxyKeyboardUx = "1";

  const isEditable = (node) => {
    if (!(node instanceof HTMLElement)) return false;
    if (node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) return true;
    if (node.isContentEditable) return true;
    if (!(node instanceof HTMLInputElement)) return false;
    return !new Set(["button", "checkbox", "radio", "file", "hidden", "submit", "reset", "range", "color"]).has(
      String(node.type || "text").toLowerCase(),
    );
  };

  let focusedEditable = isEditable(document.activeElement);
  let keyboardByViewport = false;
  let largestViewport = window.visualViewport?.height || window.innerHeight || 0;

  const sync = () => {
    body.classList.toggle("roxy-keyboard-open", focusedEditable || keyboardByViewport);
  };

  const updateViewport = () => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    largestViewport = Math.max(largestViewport, viewport.height);
    keyboardByViewport = largestViewport - viewport.height > 120;
    sync();
  };

  document.addEventListener(
    "focusin",
    (event) => {
      focusedEditable = isEditable(event.target);
      sync();
    },
    true,
  );

  document.addEventListener(
    "focusout",
    () => {
      window.setTimeout(() => {
        focusedEditable = isEditable(document.activeElement);
        sync();
      }, 0);
    },
    true,
  );

  // iOS WebKit does not fire `change` when the user chooses the same file again
  // and the input still contains that filename. React has already received the
  // FileList by the time this zero-delay cleanup runs, so resetting the native
  // control makes reference retries deterministic without touching draft state.
  document.addEventListener(
    "change",
    (event) => {
      const input = event.target;
      if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
      window.setTimeout(() => {
        try {
          input.value = "";
        } catch {}
      }, 0);
    },
    true,
  );

  window.visualViewport?.addEventListener("resize", updateViewport);
  window.visualViewport?.addEventListener("scroll", updateViewport);
  window.addEventListener("orientationchange", () => {
    window.setTimeout(() => {
      largestViewport = window.visualViewport?.height || window.innerHeight || largestViewport;
      updateViewport();
    }, 250);
  });

  updateViewport();
  sync();
})();
