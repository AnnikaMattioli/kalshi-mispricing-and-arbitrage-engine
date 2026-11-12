const status = document.getElementById("sweep-status");
const results = document.getElementById("sweep-results");
const refresh = document.getElementById("refresh-sweeps");
document.getElementById("local-sweeps").hidden = false;

function append(parent, tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  parent.append(element);
  return element;
}

function timeLabel(timestamp) {
  return new Date(timestamp).toISOString().slice(0, 19).replace("T", " ") + " UTC";
}

function ageLabel(seconds) {
  if (seconds < 60) return Math.floor(seconds) + " s";
  if (seconds < 3600) return Math.floor(seconds / 60) + " min";
  if (seconds < 86400) return Math.floor(seconds / 3600) + " hr";
  return Math.floor(seconds / 86400) + " days";
}

function showSweep(sweep) {
  const card = append(results, "article", "");
  card.className = "panel";
  append(card, "h3", sweep.series);
  const state = sweep.status === "complete" ? (sweep.stale ? "Stale" : "Recent")
    : sweep.status === "failed" ? "Sweep failed" : "Incomplete capture";
  append(card, "p", state + (sweep.captured_at
    ? " · Captured " + timeLabel(sweep.captured_at) + " · " + ageLabel(sweep.age_seconds) + " old"
    : ""));
  append(card, "p", sweep.file).className = "sweep-filename";
  if (sweep.detail) append(card, "p", sweep.detail);
  if (!sweep.counts) return;
  append(card, "p", `${sweep.counts.books_received ?? 0} of ${sweep.counts.markets_discovered ?? 0} books received`
    + (sweep.counts.request_failures ? ` · ${sweep.counts.request_failures} request failures` : ""));
  for (const event of sweep.events) {
    append(card, "h4", event.ticker);
    if (event.skipped) {
      append(card, "p", "Skipped · " + event.skipped);
      continue;
    }
    append(card, "p", Object.entries(event.decisions)
      .map(([key, count]) => count + " " + key.replaceAll("_", " ")).join(" · "));
    if (event.oldest_priced_quote_seconds != null) {
      append(card, "p", "Oldest priced quote at sweep end · "
        + event.oldest_priced_quote_seconds.toFixed(2) + " s");
    }
  }
}

async function load() {
  if (refresh.disabled) return;
  refresh.disabled = true;
  try {
    const response = await fetch("/api/sweeps", {cache: "no-store"});
    if (!response.ok) throw new Error("Dashboard server returned " + response.status);
    const report = await response.json();
    results.replaceChildren();
    for (const sweep of report.sweeps) showSweep(sweep);
    status.textContent = report.sweeps.length
      ? "Last checked " + timeLabel(report.checked_at)
      : "No saved sweeps found.";
  } catch {
    status.textContent = "Could not refresh saved sweeps. Check that the local dashboard server is running.";
  } finally {
    refresh.disabled = false;
  }
}

refresh.addEventListener("click", load);
load();
setInterval(load, 5000);
