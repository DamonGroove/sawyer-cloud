/*
 * customization/apps/branding-default/js/main.js
 *
 * Runs on every Nextcloud page. CSP-safe: no inline handlers, no third-
 * party CDN loads (CLAUDE.md §3.4 reminders). Uses addEventListener.
 *
 * Current scope (intentionally small):
 *   - Decorate the page footer with the customer slogan when Nextcloud
 *     exposes one via the theming config.
 *   - Mark the body with a data attribute so flavor CSS can scope to it.
 *
 * Adding features here should stay framework-free. No jQuery; no build
 * step. If a task needs more than vanilla DOM, stop and escalate to
 * engineering (CLAUDE.md §3.4).
 */

(function () {
    "use strict";

    var FLAVOR = "default";

    function onReady(fn) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", fn);
        } else {
            fn();
        }
    }

    function markBody() {
        if (!document.body) { return; }
        document.body.setAttribute("data-sawyer-flavor", FLAVOR);
    }

    function decorateFooter() {
        // Only on public pages (shared links / login) — logged-in pages
        // have their own Nextcloud footer handling we don't want to clobber.
        if (!document.getElementById("body-public")) { return; }
        var footer = document.getElementById("footer");
        if (!footer) { return; }
        // OC and NC expose theming values under window.OC.theme at runtime.
        var theme = (window.OC && window.OC.theme) || {};
        var slogan = theme.slogan;
        if (!slogan) { return; }
        // Check we haven't already decorated to keep this idempotent across
        // partial page re-renders.
        if (footer.querySelector("[data-sawyer-slogan]")) { return; }
        var span = document.createElement("span");
        span.setAttribute("data-sawyer-slogan", "");
        span.style.marginInlineStart = "0.75em";
        span.style.opacity = "0.8";
        span.textContent = "— " + slogan;
        footer.appendChild(span);
    }

    onReady(function () {
        try {
            markBody();
            decorateFooter();
        } catch (err) {
            // Never throw from the branding app — a broken footer must not
            // break Nextcloud for the user.
            if (window.console && window.console.warn) {
                window.console.warn("sawyer-branding:", err);
            }
        }
    });
})();
