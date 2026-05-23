/* Transpose Admin frontend — issue #100.
 *
 * MSAL.js PKCE (public client) → Entra access token → /admin/api/* fetch.
 * Static HTML is public-unlisted; the data API enforces auth.
 *
 * Configuration baked in here matches `tank-entra-auth-shipped.md`:
 *   tenantId: 48af2a40-dd60-4e0d-ba42-f0fac9a31d93
 *   clientId: 5ffe7826-3caa-41a8-9359-a5dd3aee4407
 *   scope:    api://transpose-admin/Dashboard.Read
 *
 * If those values need to change post-deploy, override via meta tags:
 *   <meta name="transpose-tenant-id" content="...">
 *   <meta name="transpose-client-id" content="...">
 *   <meta name="transpose-scope" content="...">
 */
(function () {
  "use strict";

  function meta(name, fallback) {
    var el = document.querySelector('meta[name="' + name + '"]');
    return (el && el.content) || fallback;
  }

  var TENANT_ID = meta("transpose-tenant-id", "48af2a40-dd60-4e0d-ba42-f0fac9a31d93");
  var CLIENT_ID = meta("transpose-client-id", "5ffe7826-3caa-41a8-9359-a5dd3aee4407");
  var SCOPE = meta("transpose-scope", "api://transpose-admin/Dashboard.Read");
  var API_BASE = "/admin/api";

  var msalConfig = {
    auth: {
      clientId: CLIENT_ID,
      authority: "https://login.microsoftonline.com/" + TENANT_ID,
      redirectUri: window.location.origin + "/admin/",
      navigateToLoginRequestUrl: false,
    },
    cache: {
      cacheLocation: "sessionStorage",
      storeAuthStateInCookie: false,
    },
  };

  var loginRequest = { scopes: [SCOPE] };

  /** @type {any} */
  var msalApp = null;
  var account = null;
  var booksCache = [];
  var sortKey = "created_at";
  var sortDir = "desc";

  // ── DOM helpers ─────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }

  function show(id) { var el = $(id); if (el) el.classList.remove("hidden"); }
  function hide(id) { var el = $(id); if (el) el.classList.add("hidden"); }

  function setStatus(msg) {
    var s = $("status-msg");
    if (s) s.textContent = msg || "";
  }

  function fmtUsd(v) {
    if (v == null) return "—";
    if (v === 0) return "$0.00";
    if (v < 0.01) return "$" + v.toFixed(4);
    return "$" + v.toFixed(2);
  }
  function fmtTime(seconds) {
    if (seconds == null) return "—";
    if (seconds < 60) return seconds.toFixed(1) + "s";
    var mins = Math.floor(seconds / 60);
    var sec = Math.round(seconds % 60);
    if (mins < 60) return mins + "m " + sec + "s";
    var hrs = Math.floor(mins / 60);
    var rmins = mins % 60;
    return hrs + "h " + rmins + "m";
  }
  function fmtDate(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      return d.toLocaleString();
    } catch (_) { return iso; }
  }
  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── Auth ────────────────────────────────────────────────────
  function initMsal() {
    if (!window.msal || !window.msal.PublicClientApplication) {
      setStatus("MSAL library failed to load — auth disabled.");
      return false;
    }
    msalApp = new window.msal.PublicClientApplication(msalConfig);
    return true;
  }

  async function bootstrapAuth() {
    if (!msalApp) return;
    try {
      var resp = await msalApp.handleRedirectPromise();
      if (resp && resp.account) {
        account = resp.account;
      } else {
        var accts = msalApp.getAllAccounts();
        if (accts && accts.length) account = accts[0];
      }
    } catch (e) {
      console.error("MSAL bootstrap failed", e);
    }
    renderAuthState();
    if (account) await loadBooks();
  }

  function renderAuthState() {
    if (account) {
      hide("signed-out");
      show("signed-in");
      hide("signin-btn");
      show("signout-btn");
      var u = $("auth-user");
      if (u) u.textContent = account.username || account.name || "";
    } else {
      show("signed-out");
      hide("signed-in");
      show("signin-btn");
      hide("signout-btn");
      var u2 = $("auth-user");
      if (u2) u2.textContent = "";
    }
  }

  async function signIn() {
    if (!msalApp) return;
    try {
      var resp = await msalApp.loginPopup(loginRequest);
      account = resp.account;
      renderAuthState();
      await loadBooks();
    } catch (e) {
      console.error("Sign-in failed", e);
      setStatus("Sign-in failed: " + (e && e.message ? e.message : "unknown"));
    }
  }

  async function signOut() {
    if (!msalApp || !account) return;
    try {
      await msalApp.logoutPopup({ account: account });
    } catch (e) {
      console.error("Sign-out failed", e);
    }
    account = null;
    booksCache = [];
    renderAuthState();
    renderTable([]);
  }

  async function getToken() {
    if (!msalApp || !account) throw new Error("Not signed in");
    try {
      var r = await msalApp.acquireTokenSilent({ scopes: loginRequest.scopes, account: account });
      return r.accessToken;
    } catch (e) {
      var r2 = await msalApp.acquireTokenPopup(loginRequest);
      return r2.accessToken;
    }
  }

  async function apiFetch(path) {
    var token = await getToken();
    var res = await fetch(API_BASE + path, {
      headers: { Authorization: "Bearer " + token, Accept: "application/json" },
    });
    if (!res.ok) {
      var text = "";
      try { text = await res.text(); } catch (_) {}
      throw new Error("HTTP " + res.status + ": " + text);
    }
    return await res.json();
  }

  // ── Books table ─────────────────────────────────────────────
  async function loadBooks() {
    setStatus("Loading books…");
    try {
      var data = await apiFetch("/books");
      booksCache = data.books || [];
      // Reveal quality column only if at least one book has a quality score.
      var anyQuality = booksCache.some(function (b) {
        return b.quality && b.quality.available && b.quality.score != null;
      });
      if (anyQuality) {
        show("quality-header");
        document.body.classList.add("quality-on");
      } else {
        hide("quality-header");
        document.body.classList.remove("quality-on");
      }
      renderTable(booksCache);
      setStatus(booksCache.length + " book" + (booksCache.length === 1 ? "" : "s") + " loaded.");
    } catch (e) {
      console.error("loadBooks failed", e);
      setStatus("Failed to load books: " + (e && e.message ? e.message : "unknown"));
      renderTable([]);
    }
  }

  function sortBooks(books) {
    var keyFor = {
      title: function (b) { return (b.title || "").toLowerCase(); },
      created_at: function (b) { return b.created_at || ""; },
      status: function (b) { return b.status || ""; },
      page_count: function (b) { return b.page_count || 0; },
      cost: function (b) { return (b.cost && b.cost.total_usd) || 0; },
      wall_time: function (b) { return b.wall_time_seconds || 0; },
      validation: function (b) {
        if (!b.validation) return -1;
        if (!b.validation.available) return -1;
        return b.validation.failed === 0 ? 1 : 0;
      },
      quality: function (b) { return (b.quality && b.quality.score) || -1; },
    };
    var fn = keyFor[sortKey] || keyFor.created_at;
    var sorted = books.slice().sort(function (a, b) {
      var av = fn(a), bv = fn(b);
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return sorted;
  }

  function validationCell(v) {
    if (!v || !v.available) return '<span class="validation-cell unknown">—</span>';
    var cls = v.failed === 0 ? "ok" : "bad";
    return '<span class="validation-cell ' + cls + '">' + escapeHtml(v.label) + "</span>";
  }

  function qualityCell(q) {
    if (!q || !q.available || q.score == null) return '<span class="muted">—</span>';
    var band = q.band || "";
    return (
      '<span class="quality-score band-' + escapeHtml(band) + '">' +
      '<strong>' + q.score + '</strong>' +
      (band ? ' <span class="quality-tier">' + escapeHtml(band) + '</span>' : "") +
      '</span>'
    );
  }

  function renderTable(books) {
    var tbody = $("books-tbody");
    if (!tbody) return;
    if (!books.length) {
      tbody.innerHTML = '<tr class="placeholder"><td colspan="8">No books yet.</td></tr>';
      show("empty-state");
      return;
    }
    hide("empty-state");
    var qualityOn = document.body.classList.contains("quality-on");
    var html = sortBooks(books).map(function (b) {
      var status = (b.status || "").toString();
      return (
        '<tr data-book-id="' + escapeHtml(b.id) + '">' +
        '<td>' + escapeHtml(b.title || "(untitled)") + '<div class="muted small">' + escapeHtml(b.author || "") + '</div></td>' +
        '<td>' + escapeHtml(fmtDate(b.created_at)) + '</td>' +
        '<td><span class="status-pill ' + escapeHtml(status) + '">' + escapeHtml(status) + '</span></td>' +
        '<td class="num">' + (b.page_count || 0) + '</td>' +
        '<td class="num">' + escapeHtml(fmtUsd(b.cost && b.cost.total_usd)) + '</td>' +
        '<td class="num">' + escapeHtml(fmtTime(b.wall_time_seconds)) + '</td>' +
        '<td>' + validationCell(b.validation) + '</td>' +
        (qualityOn ? '<td class="num quality-col">' + qualityCell(b.quality) + '</td>' : "") +
        '</tr>'
      );
    }).join("");
    tbody.innerHTML = html;
    Array.prototype.forEach.call(tbody.querySelectorAll("tr[data-book-id]"), function (tr) {
      tr.addEventListener("click", function () {
        openDrilldown(tr.getAttribute("data-book-id"));
      });
    });
  }

  // ── Drill-down ──────────────────────────────────────────────
  async function openDrilldown(bookId) {
    var dd = $("drilldown");
    var body = $("dd-body");
    var title = $("dd-title");
    if (!dd || !body || !title) return;
    title.textContent = "Loading…";
    body.innerHTML = '<p class="muted">Loading…</p>';
    show("drilldown");
    dd.setAttribute("aria-hidden", "false");

    try {
      var d = await apiFetch("/books/" + encodeURIComponent(bookId));
      title.textContent = d.title || bookId;
      body.innerHTML = renderDrilldown(d);
    } catch (e) {
      console.error("drilldown failed", e);
      body.innerHTML = '<p class="validation-cell bad">Failed to load: ' + escapeHtml(e.message) + '</p>';
    }
  }

  function closeDrilldown() {
    hide("drilldown");
    var dd = $("drilldown");
    if (dd) dd.setAttribute("aria-hidden", "true");
  }

  function renderDrilldown(d) {
    var stagesHtml = (d.stages || []).map(function (s) {
      var cls = s.is_total ? "total" : s.is_summary ? "summary" : "";
      return (
        '<tr class="' + cls + '">' +
        '<td>' + escapeHtml(s.name) + '</td>' +
        '<td class="num">' + escapeHtml(fmtUsd(s.cost_usd)) + '</td>' +
        '<td class="num">' + escapeHtml(fmtTime(s.wall_time_seconds)) + '</td>' +
        '<td class="note">' + escapeHtml(s.note || "") + '</td>' +
        '</tr>'
      );
    }).join("");

    var v = d.validation || {};
    var gatesHtml = (v.gates || []).map(function (g) {
      var cls = g.status === "passed" ? "pass" : g.status === "failed" ? "fail" : "notrun";
      var marker = g.status === "passed" ? "✅" : g.status === "failed" ? "❌" : "—";
      return (
        '<tr>' +
        '<td>' + escapeHtml(g.name) + '</td>' +
        '<td>' + escapeHtml(g.surfaces_after) + '</td>' +
        '<td class="' + cls + '">' + marker + " " + escapeHtml(g.status) + '</td>' +
        '<td class="num">' + (g.duration_ms != null ? g.duration_ms.toFixed(1) + " ms" : "—") + '</td>' +
        '<td class="note">' + escapeHtml(g.failure_reason || "") + '</td>' +
        '</tr>'
      );
    }).join("");

    var q = d.quality || {};
    var qualityHtml;
    if (q.available && q.score != null) {
      var band = q.band || "";
      var decompRows = (q.decomposition || []).map(function (item) {
        return (
          '<tr>' +
          '<td>' + escapeHtml(item.label || item.key || "") + '</td>' +
          '<td class="num">' + (item.score != null ? item.score : "—") + '</td>' +
          '</tr>'
        );
      }).join("");
      var sampled = (q.sampled_chunk_ids || []).length;
      qualityHtml = (
        '<p class="quality-headline">' +
        '<span class="quality-score band-' + escapeHtml(band) + '">' +
        '<strong>' + q.score + '</strong> / 100 ' +
        '<span class="quality-tier">' + escapeHtml(band) + '</span>' +
        '</span>' +
        (sampled ? ' <span class="muted small">(Layer C sampled ' + sampled + ' chunks)</span>' : "") +
        '</p>' +
        (decompRows
          ? '<table class="quality-decomp"><thead><tr><th>Sub-score</th><th class="num">0–100</th></tr></thead><tbody>' + decompRows + '</tbody></table>'
          : "")
      );
    } else {
      qualityHtml = '<p class="muted">Quality scoring not yet available. ' + escapeHtml(q.reason || "") + '</p>';
    }

    return (
      '<div class="dd-section">' +
      '<h3>Overview</h3>' +
      '<p class="muted small">Book ID: <code>' + escapeHtml(d.id) + '</code> · Status: <strong>' + escapeHtml(d.status || "") + '</strong> · Started: ' + escapeHtml(fmtDate(d.created_at)) + ' · Pages: ' + (d.page_count || 0) + '</p>' +
      '</div>' +
      '<div class="dd-section">' +
      '<h3>Pipeline stages</h3>' +
      '<table class="stages"><thead><tr><th>Stage</th><th class="num">Cost</th><th class="num">Wall-time</th><th>Notes</th></tr></thead><tbody>' + stagesHtml + '</tbody></table>' +
      '</div>' +
      '<div class="dd-section">' +
      '<h3>Quality gates (' + (v.available ? (v.passed + "/" + v.total + " passed") : "not yet run") + ')</h3>' +
      '<table class="gates"><thead><tr><th>Gate</th><th>After stage</th><th>Status</th><th class="num">Duration</th><th>Failure reason</th></tr></thead><tbody>' + gatesHtml + '</tbody></table>' +
      '</div>' +
      '<div class="dd-section">' +
      '<h3>Translation quality</h3>' + qualityHtml +
      '</div>'
    );
  }

  // ── Wiring ──────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    if (!initMsal()) return;
    $("signin-btn").addEventListener("click", signIn);
    $("signout-btn").addEventListener("click", signOut);
    $("refresh-btn").addEventListener("click", function () { loadBooks(); });
    $("dd-close").addEventListener("click", closeDrilldown);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrilldown();
    });
    // Column sort
    Array.prototype.forEach.call(document.querySelectorAll("#books-table thead th[data-sort]"), function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
        else { sortKey = key; sortDir = "desc"; }
        renderTable(booksCache);
      });
    });
    bootstrapAuth();
  });
})();
