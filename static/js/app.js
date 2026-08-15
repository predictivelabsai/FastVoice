(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-menu-toggle]");
    if (toggle) {
      document.querySelector(".sidebar")?.classList.toggle("open");
      return;
    }
    var opener = event.target.closest("[data-dialog-open]");
    if (opener) {
      document.getElementById(opener.dataset.dialogOpen)?.showModal();
    }
    var closer = event.target.closest("[data-dialog-close]");
    if (closer) {
      closer.closest("dialog")?.close();
    }
  });

  document.addEventListener("htmx:configRequest", function (event) {
    var token = document.querySelector('input[name="csrf_token"]')?.value;
    if (token) event.detail.headers["X-CSRF-Token"] = token;
  });
})();
