function bindCommandSubmit(form, commandInput, submitButton, show) {
  var isSubmitting = false;

  function beginSubmit(event) {
    if (isSubmitting) {
      event.preventDefault();
      return;
    }
    var text = String(commandInput.value || "").replace(/^\s+|\s+$/g, "");
    if (!text) {
      event.preventDefault();
      return;
    }
    isSubmitting = true;
    if (submitButton) submitButton.disabled = true;
    if (typeof show === "function") show("DYNAMIS обрабатывает поручение…");
  }

  form.addEventListener("submit", beginSubmit);
  commandInput.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    if (isSubmitting) return;
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit(submitButton || undefined);
      return;
    }
    beginSubmit({ preventDefault: function () {} });
    if (isSubmitting) form.submit();
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { bindCommandSubmit: bindCommandSubmit };
}

if (typeof document !== "undefined") {
(function () {
  var notice = document.getElementById("cr-notice");
  var messages = {
    launch: "Демонстрация интерфейса. Constructor Agent не запускается.",
    admission: "Демонстрация интерфейса. Передача в Admission не выполняется.",
    decision: "Демонстрация интерфейса. Решение человека не записывается.",
    mic: "Микрофон пока только обозначен. Голос не подключён.",
  };

  function show(text) {
    if (!notice) return;
    notice.hidden = false;
    notice.textContent = text;
  }

  document.querySelectorAll("[data-tabs]").forEach(function (root) {
    root.addEventListener("click", function (event) {
      var button = event.target.closest("[data-tab]");
      if (!button || !root.contains(button)) return;
      var name = button.getAttribute("data-tab");
      root.querySelectorAll("[data-tab]").forEach(function (item) {
        var on = item === button;
        item.classList.toggle("is-active", on);
        item.setAttribute("aria-selected", on ? "true" : "false");
      });
      var panels = root.querySelectorAll(":scope > [data-panel], :scope > .cr-bottom-body [data-panel]");
      if (!panels.length) {
        panels = root.parentElement.querySelectorAll("[data-panel]");
      }
      panels.forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-panel") !== name;
      });
    });
  });

  var detail = document.getElementById("detail-panel");
  var detailTabs = detail.querySelector("[data-tabs='detail']");
  detailTabs.addEventListener("click", function (event) {
    var button = event.target.closest("[data-tab]");
    if (!button) return;
    var name = button.getAttribute("data-tab");
    detailTabs.querySelectorAll("[data-tab]").forEach(function (item) {
      var on = item === button;
      item.classList.toggle("is-active", on);
      item.setAttribute("aria-selected", on ? "true" : "false");
    });
    detail.querySelectorAll(".cr-detail-panel").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-panel") !== name;
    });
  });

  document.querySelectorAll("[data-demo]").forEach(function (button) {
    button.addEventListener("click", function () {
      show(messages[button.getAttribute("data-demo")] || messages.decision);
    });
  });

  document.querySelectorAll("[data-later]").forEach(function (button) {
    button.addEventListener("click", function () {
      show("Раздел «" + button.getAttribute("data-later") + "» на этом шаге не подключён.");
    });
  });

  document.querySelectorAll("[data-contour]").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll("[data-contour]").forEach(function (item) {
        var on = item === button;
        item.classList.toggle("is-active", on);
        item.setAttribute("aria-pressed", on ? "true" : "false");
      });
      if (button.getAttribute("data-contour") !== "monthly") {
        show("Контур «" + button.textContent.trim() + "» на этом шаге не подключён. Открыт Monthly Commitment.");
      }
    });
  });

  var form = document.getElementById("command-form");
  var commandInput = document.getElementById("command-input");
  if (form && commandInput) {
    bindCommandSubmit(form, commandInput, form.querySelector(".cr-send"), show);
  }

  var KEY = "dynamis.control-room.layout";
  var DEFAULTS = { left: 0.24, center: 0.52, right: 0.24, bottom: 0.32 };
  var MIN = { left: 260, center: 520, right: 300, bottom: 180, top: 220 };
  var SPLIT = 12;
  var workspace = document.getElementById("cr-workspace");
  var columns = document.getElementById("cr-columns");
  var leftPane = document.getElementById("cr-left");
  var rightPane = document.getElementById("cr-right");
  var detail = document.getElementById("detail-panel");
  var collapse = document.getElementById("detail-collapse");
  var expand = document.getElementById("detail-expand");
  var drawer = { left: false, right: false };
  var state = load();

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function load() {
    var next = {
      left: DEFAULTS.left,
      right: DEFAULTS.right,
      bottom: DEFAULTS.bottom,
      leftCollapsed: false,
      rightCollapsed: false,
      bottomCollapsed: false,
    };
    try {
      var raw = window.localStorage.getItem(KEY);
      if (!raw) return next;
      var saved = JSON.parse(raw);
      ["left", "right", "bottom"].forEach(function (name) {
        var value = Number(saved[name]);
        if (isFinite(value)) next[name] = clamp(value, 0.08, 0.8);
      });
      next.leftCollapsed = Boolean(saved.leftCollapsed);
      next.rightCollapsed = Boolean(saved.rightCollapsed);
      next.bottomCollapsed = Boolean(saved.bottomCollapsed);
    } catch (error) {
      return next;
    }
    return next;
  }

  function save() {
    try {
      window.localStorage.setItem(KEY, JSON.stringify({
        left: state.left,
        right: state.right,
        bottom: state.bottom,
        leftCollapsed: state.leftCollapsed,
        rightCollapsed: state.rightCollapsed,
        bottomCollapsed: state.bottomCollapsed,
      }));
    } catch (error) {
      /* browser storage can be unavailable; the layout still works */
    }
  }

  function contentWidth() {
    var style = window.getComputedStyle(columns);
    var pad = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    return Math.max(0, columns.clientWidth - pad);
  }

  function isNarrow() {
    return window.innerWidth < 1200;
  }

  function sideClosed(side) {
    return isNarrow() ? !drawer[side] : state[side + "Collapsed"];
  }

  function apply() {
    var narrow = isNarrow();
    var full = workspace.classList.contains("is-table-full");
    var leftClosed = sideClosed("left");
    var rightClosed = sideClosed("right");
    workspace.classList.toggle("is-narrow", narrow);
    workspace.classList.toggle("is-left-collapsed", leftClosed);
    workspace.classList.toggle("is-right-collapsed", rightClosed);
    leftPane.classList.toggle("is-collapsed", leftClosed);
    rightPane.classList.toggle("is-collapsed", rightClosed);
    detail.classList.toggle("is-collapsed", state.bottomCollapsed && !full);

    leftPane.style.flex = "";
    leftPane.style.width = "";
    rightPane.style.flex = "";
    rightPane.style.width = "";
    detail.style.flex = "";
    detail.style.height = "";

    if (full) {
      workspace.style.gridTemplateRows = "minmax(0, 1fr)";
    } else if (narrow) {
      columns.style.gridTemplateColumns = "44px minmax(0, 1fr) 44px";
    } else {
      var width = contentWidth();
      var paneArea = Math.max(0, width - SPLIT * 2);
      var leftPx = leftClosed ? 44 : state.left * paneArea;
      var rightPx = rightClosed ? 44 : state.right * paneArea;
      var minsFit = paneArea >= MIN.left + MIN.center + MIN.right;
      if (minsFit) {
        if (!leftClosed) leftPx = Math.max(MIN.left, leftPx);
        if (!rightClosed) rightPx = Math.max(MIN.right, rightPx);
        var centerPx = paneArea - (leftClosed ? 44 : leftPx) - (rightClosed ? 44 : rightPx);
        if (centerPx < MIN.center) {
          var deficit = MIN.center - centerPx;
          if (!leftClosed) {
            var takeLeft = Math.min(deficit, leftPx - MIN.left);
            leftPx -= Math.max(0, takeLeft);
            deficit -= Math.max(0, takeLeft);
          }
          if (!rightClosed && deficit > 0) {
            rightPx -= Math.min(deficit, rightPx - MIN.right);
          }
        }
      } else {
        if (!leftClosed) leftPx = Math.max(160, state.left * paneArea);
        if (!rightClosed) rightPx = Math.max(160, state.right * paneArea);
        var used = (leftClosed ? 44 : leftPx) + (rightClosed ? 44 : rightPx);
        if (paneArea - used < 280) {
          var scale = Math.max(0, paneArea - 280 - (leftClosed ? 44 : 0) - (rightClosed ? 44 : 0));
          var open = (leftClosed ? 0 : leftPx) + (rightClosed ? 0 : rightPx);
          if (open > 0 && scale < open) {
            if (!leftClosed) leftPx = leftPx * scale / open;
            if (!rightClosed) rightPx = rightPx * scale / open;
          }
        }
      }
      columns.style.gridTemplateColumns = Math.round(leftPx) + "px " + SPLIT + "px minmax(0,1fr) " + SPLIT + "px " + Math.round(rightPx) + "px";
    }

    if (full) {
      workspace.style.gridTemplateRows = "minmax(0, 1fr)";
    } else if (state.bottomCollapsed) {
      workspace.style.gridTemplateRows = "minmax(0, 1fr) " + SPLIT + "px auto";
    } else {
      var height = workspace.clientHeight;
      var bottomPx = state.bottom * height;
      var limit = height - MIN.top - SPLIT;
      bottomPx = limit <= MIN.bottom ? Math.max(120, limit) : clamp(bottomPx, MIN.bottom, limit);
      workspace.style.gridTemplateRows = "minmax(0, 1fr) " + SPLIT + "px " + Math.round(bottomPx) + "px";
    }

    document.querySelector('[data-collapse="left"]').textContent = leftClosed ? "Развернуть" : "Свернуть";
    document.querySelector('[data-collapse="left"]').setAttribute("aria-expanded", leftClosed ? "false" : "true");
    document.querySelector('[data-collapse="right"]').textContent = rightClosed ? "Развернуть" : "Свернуть";
    document.querySelector('[data-collapse="right"]').setAttribute("aria-expanded", rightClosed ? "false" : "true");
    collapse.textContent = state.bottomCollapsed && !full ? "Развернуть" : "Свернуть";
    expand.textContent = full ? "Вернуть в панель" : "Открыть на весь экран";
  }

  function bindSplitter(el) {
    var axis = el.getAttribute("data-splitter");
    el.addEventListener("pointerdown", function (event) {
      if (event.button !== 0) return;
      if (workspace.classList.contains("is-table-full")) return;
      if (isNarrow() && axis !== "bottom") return;
      event.preventDefault();
      el.classList.add("is-active");
      document.body.classList.add(axis === "bottom" ? "cr-dragging-row" : "cr-dragging-col");
      if (axis === "left" && state.leftCollapsed) state.leftCollapsed = false;
      if (axis === "right" && state.rightCollapsed) state.rightCollapsed = false;
      if (axis === "bottom" && state.bottomCollapsed) state.bottomCollapsed = false;
      apply();
      var start = axis === "bottom" ? event.clientY : event.clientX;
      var width = contentWidth();
      var paneArea = Math.max(1, width - SPLIT * 2);
      var height = workspace.clientHeight;
      var startLeft = leftPane.getBoundingClientRect().width;
      var startRight = rightPane.getBoundingClientRect().width;
      var startBottom = detail.getBoundingClientRect().height;
      function move(ev) {
        if (axis === "left") {
          var next = startLeft + (ev.clientX - start);
          var maxLeft = width - MIN.center - startRight - SPLIT * 2;
          state.left = clamp(next, MIN.left, Math.max(MIN.left, maxLeft)) / paneArea;
        } else if (axis === "right") {
          var nextRight = startRight + (start - ev.clientX);
          var maxRight = width - MIN.center - startLeft - SPLIT * 2;
          state.right = clamp(nextRight, MIN.right, Math.max(MIN.right, maxRight)) / paneArea;
        } else {
          var nextBottom = startBottom + (start - ev.clientY);
          var maxBottom = height - MIN.top - SPLIT;
          state.bottom = clamp(nextBottom, MIN.bottom, Math.max(MIN.bottom, maxBottom)) / height;
        }
        apply();
      }
      function up() {
        el.classList.remove("is-active");
        document.body.classList.remove("cr-dragging-col", "cr-dragging-row");
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        save();
      }
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });
    el.addEventListener("dblclick", function () {
      if (axis === "left") {
        state.left = DEFAULTS.left;
        state.leftCollapsed = false;
      } else if (axis === "right") {
        state.right = DEFAULTS.right;
        state.rightCollapsed = false;
      } else {
        state.bottom = DEFAULTS.bottom;
        state.bottomCollapsed = false;
        workspace.classList.remove("is-table-full");
      }
      apply();
      save();
    });
  }

  document.querySelectorAll("[data-splitter]").forEach(bindSplitter);

  document.querySelectorAll("[data-collapse]").forEach(function (button) {
    button.addEventListener("click", function () {
      var side = button.getAttribute("data-collapse");
      if (isNarrow()) {
        drawer[side] = !drawer[side];
      } else {
        state[side + "Collapsed"] = !state[side + "Collapsed"];
        save();
      }
      apply();
    });
  });

  collapse.addEventListener("click", function () {
    if (workspace.classList.contains("is-table-full")) {
      workspace.classList.remove("is-table-full");
    }
    state.bottomCollapsed = !state.bottomCollapsed;
    apply();
    save();
  });

  expand.addEventListener("click", function () {
    var full = !workspace.classList.contains("is-table-full");
    workspace.classList.toggle("is-table-full", full);
    if (full) state.bottomCollapsed = false;
    apply();
    save();
  });

  document.getElementById("layout-reset").addEventListener("click", function () {
    state.left = DEFAULTS.left;
    state.right = DEFAULTS.right;
    state.bottom = DEFAULTS.bottom;
    state.leftCollapsed = false;
    state.rightCollapsed = false;
    state.bottomCollapsed = false;
    drawer.left = false;
    drawer.right = false;
    workspace.classList.remove("is-table-full");
    apply();
    save();
  });

  window.addEventListener("resize", apply);
  apply();
})();
}
