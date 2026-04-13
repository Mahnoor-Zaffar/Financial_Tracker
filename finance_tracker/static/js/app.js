const THEME_KEY = "fintrack-theme";

function getTheme() {
  return document.documentElement.getAttribute("data-theme") || "light";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(THEME_KEY, theme);
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.textContent = theme === "dark" ? "Light" : "Dark";
    button.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`);
  });
  window.dispatchEvent(new CustomEvent("fintrack:theme-change", { detail: { theme } }));
}

function syncThemeToggle(theme) {
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.textContent = theme === "dark" ? "Light" : "Dark";
    button.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`);
  });
}

function initThemeToggle() {
  syncThemeToggle(getTheme());
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      applyTheme(getTheme() === "dark" ? "light" : "dark");
    });
  });
}

function initSidebarNav() {
  const sidebar = document.querySelector("[data-sidebar]");
  const backdrop = document.querySelector("[data-sidebar-backdrop]");
  const openButton = document.querySelector("[data-nav-open]");
  if (!sidebar || !backdrop || !openButton) return;

  const open = () => {
    sidebar.classList.add("is-open");
    backdrop.classList.add("is-visible");
  };
  const close = () => {
    sidebar.classList.remove("is-open");
    backdrop.classList.remove("is-visible");
  };

  openButton.addEventListener("click", open);
  backdrop.addEventListener("click", close);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 980) close();
  });
}

function initFlashMessages() {
  document.querySelectorAll("[data-dismiss-flash]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = button.closest("[data-flash-item]");
      if (item) item.remove();
    });
  });

  const messages = document.querySelectorAll("[data-flash-item]");
  if (!messages.length) return;
  window.setTimeout(() => {
    messages.forEach((item) => item.remove());
  }, 6500);
}

function initFormLoadingStates() {
  document.querySelectorAll("form.form-auto-loading:not([data-confirm])").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!form.checkValidity()) return;
      const submitter = event.submitter || form.querySelector('[type="submit"]');
      if (!(submitter instanceof HTMLButtonElement || submitter instanceof HTMLInputElement)) return;
      submitter.disabled = true;
      submitter.classList.add("is-loading");
      if (submitter instanceof HTMLButtonElement) {
        submitter.dataset.originalText = submitter.textContent || "";
        submitter.textContent = submitter.dataset.loadingText || "Working";
      }
    });
  });
}

function initTransactionFormBehavior() {
  document.querySelectorAll("[data-transaction-form]").forEach((form) => {
    const typeField = form.querySelector('select[name$="transaction_type"]');
    const transferField = form.querySelector("[data-transfer-field]");
    const categoryField = form.querySelector("[data-category-field]");
    const transferSelect = form.querySelector('select[name$="to_account_id"]');
    const categorySelect = form.querySelector('select[name$="category_id"]');
    const categoryOptionsNode = document.getElementById("transaction-category-options");
    if (!typeField || !transferField || !categoryField) return;

    let categoryOptions = null;
    if (categoryOptionsNode) {
      try {
        categoryOptions = JSON.parse(categoryOptionsNode.textContent);
      } catch (_error) {
        categoryOptions = null;
      }
    }

    const buildCategoryOptions = (kind) => {
      if (!categorySelect) return;
      if (!categoryOptions || !Object.prototype.hasOwnProperty.call(categoryOptions, kind)) return;
      const items = kind === "transfer" ? [] : categoryOptions[kind] || [];
      const placeholderLabel = kind === "transfer" ? "No category" : "Select category";
      const currentValue = categorySelect.value;
      categorySelect.innerHTML = "";

      const placeholder = document.createElement("option");
      placeholder.value = "0";
      placeholder.textContent = placeholderLabel;
      categorySelect.appendChild(placeholder);

      items.forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = label;
        categorySelect.appendChild(option);
      });

      const hasCurrentValue = Array.from(categorySelect.options).some((option) => option.value === currentValue);
      categorySelect.value = hasCurrentValue ? currentValue : "0";
    };

    const sync = () => {
      const isTransfer = typeField.value === "transfer";
      transferField.hidden = !isTransfer;
      categoryField.hidden = isTransfer;
      if (transferSelect) transferSelect.disabled = !isTransfer;
      if (categorySelect) categorySelect.disabled = isTransfer;
      buildCategoryOptions(isTransfer ? "transfer" : typeField.value);
    };

    sync();
    typeField.addEventListener("change", sync);
  });
}

function initConfirmModal() {
  const modalRoot = document.querySelector("[data-confirm-root]");
  if (!modalRoot) return;

  const messageNode = modalRoot.querySelector("[data-confirm-message]");
  const acceptButton = modalRoot.querySelector("[data-confirm-accept]");
  const closeButtons = modalRoot.querySelectorAll("[data-confirm-close]");
  let pendingForm = null;

  const closeModal = () => {
    modalRoot.hidden = true;
    modalRoot.setAttribute("aria-hidden", "true");
    pendingForm = null;
  };

  closeButtons.forEach((button) => button.addEventListener("click", closeModal));
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modalRoot.hidden) closeModal();
  });

  if (acceptButton) {
    acceptButton.addEventListener("click", () => {
      if (!pendingForm) return;
      const form = pendingForm;
      const submitter = form.querySelector('[type="submit"]');
      if (submitter instanceof HTMLButtonElement || submitter instanceof HTMLInputElement) {
        submitter.disabled = true;
        submitter.classList.add("is-loading");
      }
      closeModal();
      form.submit();
    });
  }

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      pendingForm = form;
      if (messageNode) {
        messageNode.textContent = form.getAttribute("data-confirm") || "Are you sure?";
      }
      modalRoot.hidden = false;
      modalRoot.setAttribute("aria-hidden", "false");
      if (acceptButton instanceof HTMLElement) acceptButton.focus();
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
  initSidebarNav();
  initFlashMessages();
  initFormLoadingStates();
  initTransactionFormBehavior();
  initConfirmModal();
});
