// Interaksi global sederhana. Chart dibuat pada template masing-masing halaman.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach(form => {
    form.addEventListener("submit", () => {
      const submit = form.querySelector('button[type="submit"],button:not([type])');
      if (submit && !form.hasAttribute("onsubmit")) {
        submit.dataset.originalText = submit.textContent;
      }
    });
  });
});
