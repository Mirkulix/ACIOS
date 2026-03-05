/* ============================================
   NEXUS AI Dashboard - Frontend Logic v5
   WebSocket Push + Fallback Polling
   Live Process Monitor
   ============================================ */

(function () {
    "use strict";

    var agents = [];
    var tasks = [];
    var messages = [];
    var kpis = [];
    var reports = [];
    var activityFeed = [];
    var ws = null;
    var wsConnected = false;
    var pollTimer = null;

    // Track latest agent activity state for card overlays
    var agentActivityState = {};

    var ROLE_COLORS = {
        ceo: "#e74c3c", cfo: "#2ecc71", cto: "#3498db",
        sales: "#f39c12", marketing: "#9b59b6", support: "#1abc9c",
        operations: "#e67e22", developer: "#2980b9", hr: "#95a5a6",
    };

    var $ = function (sel) { return document.querySelector(sel); };
    var el = function (tag, attrs) {
        var node = document.createElement(tag);
        var children = Array.prototype.slice.call(arguments, 2);
        if (attrs) {
            for (var k in attrs) {
                if (!attrs.hasOwnProperty(k)) continue;
                var v = attrs[k];
                if (k === "className") node.className = v;
                else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
                else if (k.startsWith("on")) node.addEventListener(k.slice(2).toLowerCase(), v);
                else node.setAttribute(k, v);
            }
        }
        for (var i = 0; i < children.length; i++) {
            var child = children[i];
            if (typeof child === "string") node.appendChild(document.createTextNode(child));
            else if (child) node.appendChild(child);
        }
        return node;
    };

    // --- Helpers ---
    function thinkingDots() {
        return el("span", { className: "thinking-dots" },
            el("span", { className: "dot" }),
            el("span", { className: "dot" }),
            el("span", { className: "dot" })
        );
    }

    // --- API ---
    function api(path, opts) {
        return fetch("/api/" + path, opts)
            .then(function (res) {
                if (!res.ok) throw new Error("HTTP " + res.status);
                return res.json();
            })
            .catch(function (err) {
                console.error("API error (" + path + "):", err);
                return null;
            });
    }

    // --- Fetch All Data ---
    function fetchAll() {
        return Promise.all([
            api("agents"), api("tasks"), api("messages"),
            api("kpis"), api("reports"), api("status"),
            api("activity-feed"),
        ]).then(function (results) {
            if (results[0]) agents = results[0];
            if (results[1]) tasks = results[1];
            if (results[2]) messages = results[2];
            if (results[3]) kpis = results[3];
            if (results[4]) reports = results[4];
            if (results[5]) updateLiveStatus(results[5]);
            if (results[6]) activityFeed = results[6];
            renderAll();
        }).catch(function (err) {
            console.error("fetchAll error:", err);
        });
    }

    function updateLiveStatus(status) {
        var dot = $(".status-dot");
        var label = $(".ws-label");
        if (!dot || !label) return;
        if (status && status.live) {
            dot.style.background = "var(--accent-green)";
            var mode = wsConnected ? "LIVE (Push)" : "LIVE (Poll)";
            label.textContent = mode + " \u2014 " + (status.agent_count || 0) + " Agents | " + (status.task_count || 0) + " Tasks";
        } else {
            dot.style.background = "var(--accent-yellow)";
            label.textContent = "Orchestrator Offline";
        }
    }

    // --- Render: Agents ---
    function renderAgents() {
        var grid = $(".agent-grid");
        if (!grid) return;
        grid.innerHTML = "";
        agents.forEach(function (agent) {
            var color = ROLE_COLORS[agent.role] || agent.color || "#888";
            var statusClass = agent.enabled !== false ? (agent.status || "idle") : "disabled";

            // Determine live activity state
            var activity = agentActivityState[agent.name];
            var activityClass = "";
            var activityLine = null;
            if (activity && agent.status === "working") {
                var evType = activity.event_type;
                if (evType === "agent_thinking") {
                    activityClass = " thinking";
                    activityLine = el("div", { className: "agent-activity-line" },
                        "\uD83E\uDDE0 Denkt nach",
                        thinkingDots()
                    );
                } else if (evType === "agent_tool_call") {
                    activityClass = " tool-calling";
                    var toolName = (activity.detail || "").split(":")[0];
                    activityLine = el("div", { className: "agent-activity-line", style: { color: "var(--accent-blue)" } },
                        "\uD83D\uDD27 Tool: " + toolName
                    );
                } else if (evType === "agent_tool_result") {
                    activityClass = " tool-calling";
                    activityLine = el("div", { className: "agent-activity-line", style: { color: "var(--accent-green)" } },
                        "\u2705 Tool-Ergebnis"
                    );
                } else if (evType === "agent_response") {
                    activityLine = el("div", { className: "agent-activity-line", style: { color: "var(--accent-green)" } },
                        "\u2705 Antwort erhalten"
                    );
                }
            }

            var card = el("div", {
                className: "agent-card" + (agent.enabled === false ? " disabled" : "") + activityClass,
                style: { "--agent-color": color },
                onClick: function () { showAgentDetail(agent); },
            },
                el("div", { className: "agent-name" }, agent.name || "?"),
                el("div", { className: "agent-role" }, (agent.role || "").toUpperCase()),
                el("div", { className: "agent-status" },
                    el("span", { className: "agent-status-dot " + statusClass }),
                    el("span", null, statusClass.charAt(0).toUpperCase() + statusClass.slice(1))
                ),
                agent.current_task ? el("div", { className: "agent-task" }, agent.current_task) : null,
                activityLine,
                el("div", { className: "agent-completed" }, (agent.tasks_completed || 0) + " Tasks erledigt")
            );
            grid.appendChild(card);
        });
    }

    // --- Render: Tasks (Kanban) ---
    function renderTasks() {
        var colPending = $(".kanban-column.pending .kanban-cards");
        var colProgress = $(".kanban-column.in-progress .kanban-cards");
        var colDone = $(".kanban-column.completed .kanban-cards");
        if (!colPending || !colProgress || !colDone) return;

        colPending.innerHTML = "";
        colProgress.innerHTML = "";
        colDone.innerHTML = "";

        var counts = { pending: 0, in_progress: 0, completed: 0 };

        tasks.forEach(function (task) {
            var status = task.status || "pending";
            var col;
            if (status === "completed") { col = colDone; counts.completed++; }
            else if (status === "in_progress") { col = colProgress; counts.in_progress++; }
            else { col = colPending; counts.pending++; }

            var hasResult = task.result && task.result.length > 0;
            var card = el("div", {
                className: "task-card" + (hasResult ? " has-result" : "") + (status === "in_progress" ? " working" : ""),
                onClick: function () { showTaskDetail(task); },
            },
                el("div", { className: "task-title" }, task.title || "Untitled"),
                task.description
                    ? el("div", { className: "task-description" }, task.description.substring(0, 120))
                    : null,
                el("div", { className: "task-meta" },
                    el("span", { className: "task-assignee" }, task.assigned_to || "Auto"),
                    el("span", { className: "task-priority " + (task.priority || "medium") }, task.priority || "medium")
                ),
                status === "in_progress"
                    ? el("div", { className: "task-working-indicator" }, "Wird bearbeitet...")
                    : null,
                hasResult
                    ? el("div", { className: "task-result-preview" }, "Ergebnis anzeigen \u2192")
                    : null
            );
            col.appendChild(card);
        });

        var cP = $(".kanban-column.pending .count");
        var cI = $(".kanban-column.in-progress .count");
        var cC = $(".kanban-column.completed .count");
        if (cP) cP.textContent = counts.pending;
        if (cI) cI.textContent = counts.in_progress;
        if (cC) cC.textContent = counts.completed;

        var total = $("#task-total");
        if (total) total.textContent = tasks.length + " Tasks";
    }

    // --- Show Task Detail Modal ---
    function showTaskDetail(task) {
        var overlay = $(".task-modal-overlay");
        if (!overlay) return;
        var title = $(".task-modal-title");
        var meta = $(".task-modal-meta");
        var result = $(".task-modal-result");
        if (title) title.textContent = task.title || "Task";
        if (meta) {
            meta.innerHTML = "";
            var rows = [
                ["Status", (task.status || "?").toUpperCase()],
                ["Agent", task.assigned_to || "Auto"],
                ["Prioritaet", (task.priority || "medium").toUpperCase()],
                ["Erstellt von", task.created_by || "Dashboard"],
            ];
            if (task.created_at) rows.push(["Erstellt", new Date(task.created_at).toLocaleString("de-DE")]);
            if (task.completed_at) rows.push(["Abgeschlossen", new Date(task.completed_at).toLocaleString("de-DE")]);
            rows.forEach(function (r) {
                meta.appendChild(el("div", { className: "modal-detail-row" },
                    el("span", { className: "modal-detail-label" }, r[0]),
                    el("span", { className: "modal-detail-value" }, r[1])
                ));
            });
        }
        if (result) {
            result.textContent = task.result || "Noch kein Ergebnis.";
        }
        overlay.classList.add("active");
    }

    function closeTaskModal() {
        var overlay = $(".task-modal-overlay");
        if (overlay) overlay.classList.remove("active");
    }

    // --- Render: Messages ---
    function renderMessages() {
        var list = $(".message-list");
        if (!list) return;
        list.innerHTML = "";
        var sorted = messages.slice().reverse();
        if (sorted.length === 0) {
            list.appendChild(el("div", { className: "empty-state" }, "Noch keine Nachrichten."));
            return;
        }
        sorted.forEach(function (msg) {
            var typeClass = (msg.message_type || "direct").toLowerCase();
            var time = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString("de-DE") : "";
            list.appendChild(el("div", { className: "message-item" },
                el("div", { className: "message-header" },
                    el("span", { className: "message-from" }, msg.from_agent || "?"),
                    el("span", { className: "message-arrow" }, "\u2192"),
                    el("span", { className: "message-to" }, msg.to_agent || "alle"),
                    el("span", { className: "message-type-badge " + typeClass }, typeClass)
                ),
                el("div", { className: "message-content" }, msg.content || ""),
                time ? el("div", { className: "message-time" }, time) : null
            ));
        });
    }

    // --- Render: KPIs ---
    function renderKPIs() {
        var grid = $(".kpi-grid");
        if (!grid) return;
        grid.innerHTML = "";
        if (kpis.length === 0) {
            grid.appendChild(el("div", { className: "empty-state" }, "Noch keine KPIs."));
            return;
        }
        kpis.forEach(function (kpi) {
            var pct = kpi.target > 0 ? Math.min((kpi.value / kpi.target) * 100, 100) : 0;
            var barClass = pct >= 100 ? "over" : pct >= 75 ? "on-track" : "behind";
            var displayValue = kpi.value >= 1000 ? (kpi.value / 1000).toFixed(0) + "K" : (Number.isInteger(kpi.value) ? kpi.value : kpi.value.toFixed(1));
            grid.appendChild(el("div", { className: "kpi-card" },
                el("div", { className: "kpi-name" }, kpi.name),
                el("div", { className: "kpi-value" }, String(displayValue)),
                el("div", { className: "kpi-bar-track" },
                    el("div", { className: "kpi-bar-fill " + barClass, style: { width: pct + "%" } })
                ),
                el("div", { className: "kpi-target" }, "Ziel: " + (kpi.target || 0).toLocaleString() + (kpi.agent_role ? " | " + kpi.agent_role.toUpperCase() : ""))
            ));
        });
    }

    // --- Render: Reports ---
    function renderReports() {
        var list = $(".report-list");
        if (!list) return;
        list.innerHTML = "";
        if (reports.length === 0) {
            list.appendChild(el("div", { className: "empty-state" }, "Keine Berichte vorhanden."));
            return;
        }
        reports.forEach(function (report) {
            var sizeKB = (report.size / 1024).toFixed(1);
            var modified = new Date(report.modified).toLocaleString("de-DE");
            var ext = report.extension || "";
            list.appendChild(el("div", {
                className: "report-card",
                onClick: function () { openReport(report.filename); },
            },
                el("div", { className: "report-card-name" }, report.filename.replace(/_/g, " ").replace(/\.\w+$/, "")),
                el("div", { className: "report-card-meta" },
                    el("span", null, sizeKB + " KB"),
                    el("span", null, modified)
                ),
                el("div", null, el("span", { className: "report-card-badge" }, ext.replace(".", "").toUpperCase() || "FILE"))
            ));
        });
    }

    function openReport(filename) {
        var overlay = $(".report-modal-overlay");
        if (!overlay) return;
        $(".report-modal-title").textContent = filename.replace(/_/g, " ");
        $(".report-content").textContent = "Wird geladen...";
        overlay.classList.add("active");
        api("reports/" + encodeURIComponent(filename)).then(function (data) {
            $(".report-content").textContent = (data && data.content) ? data.content : "Fehler beim Laden.";
        });
    }

    function closeReportModal() {
        var overlay = $(".report-modal-overlay");
        if (overlay) overlay.classList.remove("active");
    }

    // --- Activity Feed: event type config ---
    var ACTIVITY_ICONS = {
        agent_task_started: "\u26A1",
        agent_thinking: "\uD83E\uDDE0",
        agent_tool_call: "\uD83D\uDD27",
        agent_tool_result: "\u2705",
        agent_response: "\u2705",
    };

    var ACTIVITY_LABELS = {
        agent_task_started: "Task gestartet",
        agent_thinking: "Anfrage an LLM",
        agent_tool_call: "Tool-Aufruf",
        agent_tool_result: "Tool-Ergebnis",
        agent_response: "Antwort erhalten",
    };

    // --- Render: Activity Feed ---
    function renderActivityFeed() {
        var feed = $("#activity-feed");
        if (!feed) return;
        var counter = $("#activity-count");
        if (counter) counter.textContent = activityFeed.length + " Events";

        // Check if user is scrolled near bottom before re-rendering
        var wasAtBottom = feed.scrollTop + feed.clientHeight >= feed.scrollHeight - 30;

        if (activityFeed.length === 0) {
            feed.innerHTML = "";
            feed.appendChild(el("div", { className: "empty-state" }, "Warte auf Agent-Aktivitaet..."));
            return;
        }

        feed.innerHTML = "";
        activityFeed.forEach(function (entry) {
            var evType = entry.event_type || "activity";
            var icon = ACTIVITY_ICONS[evType] || "\u2022";
            var label = ACTIVITY_LABELS[evType] || evType;
            var time = "";
            if (entry.timestamp) {
                try { time = new Date(entry.timestamp).toLocaleTimeString("de-DE"); } catch (e) { time = ""; }
            }
            var agentColor = entry.color || "#888";
            var detailText = icon + " " + label;
            if (entry.detail) detailText += " \u2014 " + entry.detail;

            var isThinking = evType === "agent_thinking";

            var row = el("div", { className: "activity-entry " + evType },
                el("span", { className: "activity-time" }, time),
                el("span", { className: "activity-agent", style: { color: agentColor } }, entry.agent || "SYSTEM"),
                el("span", { className: "activity-detail" },
                    detailText,
                    isThinking ? thinkingDots() : null
                )
            );
            feed.appendChild(row);
        });

        // Auto-scroll to bottom only if user was already at the bottom
        if (wasAtBottom) {
            feed.scrollTop = feed.scrollHeight;
        }
    }

    // --- Add single activity entry (from WebSocket push) ---
    function addActivityEntry(entry) {
        activityFeed.push(entry);
        // Cap at 200
        if (activityFeed.length > 200) activityFeed = activityFeed.slice(-200);

        // Track latest state per agent for card overlays
        if (entry.agent) {
            agentActivityState[entry.agent] = entry;
        }

        renderActivityFeed();
        renderAgents(); // Re-render agent cards with updated activity state
    }

    // --- Render All ---
    function renderAll() {
        try { renderAgents(); } catch (e) { console.error("renderAgents:", e); }
        try { renderActivityFeed(); } catch (e) { console.error("renderActivityFeed:", e); }
        try { renderTasks(); } catch (e) { console.error("renderTasks:", e); }
        try { renderMessages(); } catch (e) { console.error("renderMessages:", e); }
        try { renderKPIs(); } catch (e) { console.error("renderKPIs:", e); }
        try { renderReports(); } catch (e) { console.error("renderReports:", e); }
    }

    // --- Agent Detail Modal ---
    function showAgentDetail(agent) {
        var overlay = $(".modal-overlay");
        if (!overlay) return;
        var color = ROLE_COLORS[agent.role] || "#888";
        $(".modal-title").textContent = agent.name;
        $(".modal-title").style.color = color;
        var detail = $(".modal-detail");
        detail.innerHTML = "";
        var rows = [
            ["Rolle", (agent.role || "").toUpperCase()],
            ["Model", agent.model || "N/A"],
            ["Status", agent.status || "idle"],
            ["Aktueller Task", agent.current_task || "Keiner"],
            ["Tasks erledigt", String(agent.tasks_completed || 0)],
            ["Aktiv", agent.enabled !== false ? "Ja" : "Nein"],
        ];
        rows.forEach(function (r) {
            detail.appendChild(el("div", { className: "modal-detail-row" },
                el("span", { className: "modal-detail-label" }, r[0]),
                el("span", { className: "modal-detail-value" }, r[1])
            ));
        });
        overlay.classList.add("active");
    }

    function closeModal() {
        var overlay = $(".modal-overlay");
        if (overlay) overlay.classList.remove("active");
    }

    // --- Task Creation ---
    function handleTaskSubmit(e) {
        e.preventDefault();
        var title = $("#task-title").value.trim();
        var desc = $("#task-desc").value.trim();
        var assignee = $("#task-assignee").value;
        var priority = $("#task-priority").value;
        if (!title) return;

        api("tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: title, description: desc, assigned_to: assignee, priority: priority }),
        }).then(function (result) {
            if (result) {
                showToast("Task erstellt: " + title);
                e.target.reset();
                fetchAll();
            }
        });
    }

    function showToast(message) {
        var toast = $(".toast");
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add("visible");
        setTimeout(function () { toast.classList.remove("visible"); }, 3000);
    }

    // --- WebSocket (Push Mode) ---
    function connectWebSocket() {
        var proto = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(proto + "//" + location.host + "/ws");

        ws.onopen = function () {
            console.log("WS connected — switching to push mode");
            wsConnected = true;
            // Stop polling when WebSocket is active
            if (pollTimer) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        };

        ws.onclose = function () {
            console.log("WS disconnected — falling back to polling");
            wsConnected = false;
            startPolling();
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = function () { ws.close(); };

        ws.onmessage = function (event) {
            try {
                var data = JSON.parse(event.data);
                handlePushEvent(data);
            } catch (e) {
                console.error("WS parse error:", e);
            }
        };
    }

    function handlePushEvent(data) {
        var type = data.type;

        // Activity feed events — add directly without full refresh
        if (type === "agent_thinking" || type === "agent_tool_call" || type === "agent_tool_result" || type === "agent_response" || type === "agent_task_started") {
            addActivityEntry(data);
            return;
        }

        if (type === "task_in_progress" || type === "task_completed" || type === "task_failed" || type === "task_updated" || type === "task_created") {
            // Refresh all data on any task state change
            // Also clear activity state for completed/failed agents
            if (type === "task_completed" || type === "task_failed") {
                // Clear the agent activity state since task is done
                var taskId = data.task_id;
                if (data.task && data.task.assigned_to) {
                    delete agentActivityState[data.task.assigned_to];
                }
            }
            fetchAll();
        } else if (type === "pong") {
            // Heartbeat response, ignore
        } else {
            // Unknown event type — refresh to be safe
            fetchAll();
        }
    }

    function startPolling() {
        if (pollTimer) return;
        pollTimer = setInterval(fetchAll, 3000);
    }

    // --- Populate Assignee Dropdown ---
    function populateAssigneeDropdown() {
        var select = $("#task-assignee");
        if (!select) return;
        while (select.options.length > 1) select.remove(1);
        agents.forEach(function (agent) {
            if (agent.enabled !== false) {
                var opt = document.createElement("option");
                opt.value = agent.name;
                opt.textContent = agent.name + " (" + (agent.role || "").toUpperCase() + ")";
                select.appendChild(opt);
            }
        });
    }

    // --- Init ---
    function init() {
        var form = $(".task-form");
        if (form) form.addEventListener("submit", handleTaskSubmit);

        // Close modals
        var closeBtn = $(".modal-close");
        if (closeBtn) closeBtn.addEventListener("click", closeModal);
        var overlay = $(".modal-overlay");
        if (overlay) overlay.addEventListener("click", function (e) { if (e.target === overlay) closeModal(); });

        var reportCloseBtn = $(".report-modal-close");
        if (reportCloseBtn) reportCloseBtn.addEventListener("click", closeReportModal);
        var reportOverlay = $(".report-modal-overlay");
        if (reportOverlay) reportOverlay.addEventListener("click", function (e) { if (e.target === reportOverlay) closeReportModal(); });

        var taskCloseBtn = $(".task-modal-close");
        if (taskCloseBtn) taskCloseBtn.addEventListener("click", closeTaskModal);
        var taskOverlay = $(".task-modal-overlay");
        if (taskOverlay) taskOverlay.addEventListener("click", function (e) { if (e.target === taskOverlay) closeTaskModal(); });

        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") { closeModal(); closeReportModal(); closeTaskModal(); }
        });

        // Initial data fetch
        fetchAll().then(function () {
            populateAssigneeDropdown();
        });

        // Connect WebSocket (stops polling when connected)
        connectWebSocket();

        // Start polling as fallback until WebSocket connects
        startPolling();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
