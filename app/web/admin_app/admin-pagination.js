(() => {
  "use strict";
  window.createAdminPagination = () => {
    const pages = new Map();
    return {
      page(name, filters, limit = 50) {
        if (filters !== undefined || !pages.has(name)) {
          const values = { ...(filters || {}) };
          values.offset = Math.max(0, Math.min(100000, Number(values.offset) || 0));
          pages.set(name, values);
        }
        const values = { ...pages.get(name) };
        const params = new URLSearchParams({ limit: String(limit), offset: String(values.offset) });
        for (const [key, value] of Object.entries(values)) {
          if (key !== "offset" && key !== "limit" && value !== "" && value != null) params.set(key, String(value));
        }
        return {
          filters: values, params,
          controls(data, onPage) {
            const controls = document.createElement("nav");
            controls.className = "admin-pagination";
            controls.setAttribute("aria-label", "Страницы: " + name);
            const offset = values.offset;
            const count = (data.items || []).length;
            const total = Number.isFinite(data.total) ? data.total : null;
            const more = typeof data.has_more === "boolean" ? data.has_more
              : total !== null ? offset + count < total : count === limit;
            const status = document.createElement("span");
            status.className = "muted";
            status.setAttribute("role", "status");
            status.textContent = count ? "Записи " + (offset + 1) + "–" + (offset + count) : "На этой странице записей нет";
            if (total !== null) status.textContent += " · всего " + total;
            const error = document.createElement("span");
            error.className = "form-message error";
            error.setAttribute("role", "alert");
            const makeButton = (title, nextOffset, disabled) => {
              const button = document.createElement("button");
              button.type = "button";
              button.className = "table-action secondary";
              button.textContent = title;
              button.disabled = disabled;
              button.addEventListener("click", async () => {
                for (const item of controls.querySelectorAll("button")) item.disabled = true;
                error.textContent = "";
                try { await onPage({ ...values, offset: nextOffset }); }
                catch (cause) { error.textContent = cause.message || "Не удалось загрузить страницу"; }
                finally {
                  previous.disabled = offset === 0;
                  next.disabled = !more || offset + limit > 100000;
                }
              });
              return button;
            };
            const previous = makeButton("Предыдущая страница", Math.max(0, offset - limit), offset === 0);
            const next = makeButton("Следующая страница", offset + limit, !more || offset + limit > 100000);
            controls.append(previous, status, next, error);
            return controls;
          },
        };
      },
      reset() { pages.clear(); },
    };
  };
})();
