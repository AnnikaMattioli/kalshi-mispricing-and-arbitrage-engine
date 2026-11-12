const $ = (id) => document.getElementById(id);
const title = (value) => value.replaceAll("_", " ");
const dollars = (value) => value == null ? "—" : new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD",
}).format(Number(value));
const seconds = (value) => value == null ? "—" : Number(value).toFixed(2) + " s";
const utc = (value) => new Date(value).toISOString().slice(0, 19).replace("T", " ") + " UTC";
let demo, replay, model, times, index, playing;

function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text != null) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function svgNode(tag, attributes, text) {
  const item = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, value);
  if (text != null) item.textContent = text;
  return item;
}

function table(headers, rows) {
  const result = node("table");
  const heading = node("tr");
  for (const name of headers) {
    const th = node("th", name);
    th.scope = "col";
    heading.append(th);
  }
  const head = node("thead");
  head.append(heading);
  const body = node("tbody");
  appendRows(body, rows);
  result.append(head, body);
  return result;
}

function appendRows(body, rows) {
  body.replaceChildren();
  for (const cells of rows) {
    const row = node("tr");
    for (const value of cells) row.append(node("td", value));
    body.append(row);
  }
}

function options(select, items, preferred) {
  select.replaceChildren();
  for (const [value, label] of items) select.add(new Option(label, value));
  if (items.some(([value]) => value === preferred)) select.value = preferred;
}

function showReplay(report, source) {
  stop();
  replay = report;
  times = [...new Set(report.plans.map((item) => item.signal_at))].sort();
  $("replay-source").textContent = source;
  $("timeline").max = Math.max(0, times.length - 1);
  $("timeline").disabled = !times.length;
  $("play").disabled = times.length < 2;
  options($("scenario"), report.scenarios.map((scenario) => [scenario.name, title(scenario.name)]));
  $("scenario-counts").replaceChildren(table(
    ["Assumption", "Priced plans", "Full bundles", "Residual", "Beyond capture", "Positive survivors"],
    Object.entries(report.scenario_counts).map(([name, row]) => [title(name), row.priced_plans,
      row.full_bundles, row.with_residual_exposure, row.beyond_capture, row.positive_candidates_surviving]),
  ));
  setIndex(0);
}

function setIndex(next) {
  index = Math.max(0, Math.min(next, times.length - 1));
  $("timeline").value = index;
  $("prev").disabled = index === 0;
  $("next").disabled = index >= times.length - 1;
  $("time-label").textContent = times.length ? utc(times[index]) : "No priced snapshots";
  const plans = replay.plans.filter((item) => item.signal_at === times[index]);
  const labels = plans.map(({ conditional_full_fill: plan }, position) => [
    String(position), title(plan.strategy) + " · " + plan.legs.map((leg) => leg.ticker).join(" / "),
  ]);
  options($("plan"), labels, labels.find(([, label]) => label.startsWith("outcome basket"))?.[0]);
  $("plan").disabled = !plans.length;
  showPlan();
}

function showPlan() {
  const plans = replay.plans.filter((item) => item.signal_at === times[index]);
  const plan = plans[Number($("plan").value)];
  if (!plan) {
    $("summary").replaceChildren();
    $("legs").replaceChildren();
    $("execution-note").textContent = "This report contains no plans with both quotes and depth.";
    return;
  }
  const conditional = plan.conditional_full_fill;
  const execution = plan.execution[$("scenario").value];
  if (!execution) {
    $("summary").replaceChildren();
    $("legs").replaceChildren();
    $("execution-note").textContent = "This plan has no result for the selected assumption.";
    return;
  }
  const fields = [
    ["Ordinary floor if all fill", conditional.ordinary_payout_floor],
    ["Conservative floor if all fill", conditional.conservative_payout_floor],
    ["Simulated debit", execution.debit],
    ["Simulated net lower bound", execution.net_lower_bound],
  ];
  $("summary").replaceChildren(...fields.map(([label, value]) => {
    const card = node("div", null, "metric");
    card.append(node("span", label), node("strong", dollars(value)));
    return card;
  }));
  const assumption = replay.scenarios.find((scenario) => scenario.name === $("scenario").value);
  $("execution-note").textContent = [
    execution.full_bundle_filled ? "All legs filled." : "Full bundle did not fill.",
    execution.has_residual_exposure ? "Residual exposure remains." : "No unpaired exposure.",
    "Matched quantity " + execution.matched_quantity + " · receipt span " + seconds(execution.filled_quote_span_seconds) + ".",
    assumption && assumption.participation != null
      ? `${assumption.delay_seconds} s delay · ${assumption.leg_gap_seconds} s leg gap · ${Number(assumption.participation) * 100}% displayed depth.`
      : "",

  ].join(" ");
  appendRows($("legs"), execution.legs.map((leg) => {
    const debit = (leg.fills || []).reduce((sum, fill) => sum + Number(fill.price) * Number(fill.quantity)
      + Number(fill.trade_fee) + Number(fill.rounding_fee) - Number(fill.rebate), 0);
    return [leg.leg.ticker, leg.leg.side.toUpperCase(), dollars(leg.limit), leg.filled, leg.residual,
      seconds(leg.quote_age_seconds), dollars(debit), title(leg.status)];
  }));
}

function stop() {
  clearInterval(playing);
  playing = null;
  $("play").textContent = "Play";
}

function chart(label, width, height) {
  return svgNode("svg", {viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": label});
}

function showModel(report, source) {
  model = report;
  $("model-source").textContent = source;
  const forecasts = [["Model", "model", "model"], ["Market midpoint", "midpoint", "baseline"]];
  const brier = chart("Brier score bars for model and market midpoint", 360, 145);
  for (const [i, [label, key, style]] of forecasts.entries()) {
    const score = model.metrics[key].brier;
    const y = 25 + i * 60;
    brier.append(svgNode("text", {x: 10, y}, label + "  " + score.toFixed(5)),
      svgNode("rect", {x: 10, y: y + 12, width: 330 * score, height: 15, rx: 3, class: style}));
  }
  $("brier").replaceChildren(brier);
  const calibration = chart("Calibration scatter plot with diagonal reference and bin counts", 360, 270);
  const x = (p) => 48 + p * 265;
  const y = (p) => 220 - p * 185;
  calibration.append(svgNode("path", {d: "M48 35V220H313", fill: "none", class: "axis"}),
    svgNode("line", {x1: x(0), y1: y(0), x2: x(1), y2: y(1), class: "ideal"}),
    svgNode("text", {x: 160, y: 252}, "Mean probability"),
    svgNode("text", {x: 48, y: 24}, "Observed frequency"));
  for (const p of [0, .5, 1]) {
    calibration.append(svgNode("text", {x: x(p), y: 239, "text-anchor": "middle"}, p),
      svgNode("text", {x: 38, y: y(p) + 4, "text-anchor": "end"}, p));
  }
  const binRows = [];
  for (const [i, [label, key, style]] of forecasts.entries()) {
    calibration.append(svgNode("circle", {cx: 178 + i * 69, cy: 18, r: 4, class: style}),
      svgNode("text", {x: 188 + i * 69, y: 22}, i ? "Midpoint" : "Model"));
    for (const bin of model.metrics[key].calibration) {
      if (!bin.n) continue;
      const cx = x(bin.mean_probability);
      const cy = y(bin.observed_frequency);
      calibration.append(svgNode("circle", {cx, cy, r: 4, class: style}),
        svgNode("text", {x: cx + 6, y: cy + (i ? 13 : -6)}, bin.n));
      binRows.push([label, `${Math.round(bin.lower * 100)}–${Math.round(bin.upper * 100)}%`, bin.n,
        (bin.mean_probability * 100).toFixed(1) + "%", (bin.observed_frequency * 100).toFixed(1) + "%"]);
    }
  }
  $("calibration").replaceChildren(calibration);
  $("calibration-table").replaceChildren(table(["Forecast", "Bin", "N", "Mean", "Observed"], binRows));
  $("model-note").textContent = `${model.train_games} training rows · ${model.holdout_games} holdout rows · ${model.depth_matched_games} holdout rows with matching depth`;
}

function isReplay(report) {
  return Array.isArray(report?.plans) && Array.isArray(report.scenarios) && report.scenarios.length
    && report.scenarios.every((scenario) => typeof scenario.name === "string")
    && report.scenario_counts && report.plans.every((plan) => Number.isFinite(Date.parse(plan.signal_at))
      && Array.isArray(plan.conditional_full_fill?.legs) && plan.execution);
}

function isModel(report) {
  return ["model", "midpoint"].every((key) => {
    const item = report?.metrics?.[key];
    return Number.isFinite(item?.brier) && Array.isArray(item.calibration)
      && item.calibration.every((bin) => Number.isFinite(bin.n) && (!bin.n
        || [bin.lower, bin.upper, bin.mean_probability, bin.observed_frequency].every(Number.isFinite)));
  });
}

function reset() {
  $("source").textContent = "Synthetic demo";
  $("file-status").textContent = "";
  $("file").value = "";
  showReplay(demo.replay, "Synthetic replay");
  showModel(demo.model, "Synthetic holdout");
}

$("file").addEventListener("change", async (event) => {
  const [file] = event.target.files;
  if (!file) return;
  try {
    if (file.size > 25_000_000) throw new Error("File exceeds 25 MB");
    const report = JSON.parse(await file.text());
    if (isReplay(report)) showReplay(report, "Local replay report");
    else if (isModel(report)) showModel(report, "Local model report");
    else throw new Error("Expected a replay or model report");
    $("source").textContent = "Local report loaded";
    $("file-status").textContent = "Opened " + file.name;
  } catch (error) {
    reset();
    $("file-status").textContent = "Could not open report. " + error.message;
  }
});
$("reset").addEventListener("click", reset);
$("prev").addEventListener("click", () => { stop(); setIndex(index - 1); });
$("next").addEventListener("click", () => { stop(); setIndex(index + 1); });
$("timeline").addEventListener("input", (event) => { stop(); setIndex(Number(event.target.value)); });
$("plan").addEventListener("change", showPlan);
$("scenario").addEventListener("change", showPlan);
$("play").addEventListener("click", () => {
  if (playing) return stop();
  if (index >= times.length - 1) setIndex(0);
  $("play").textContent = "Pause";
  playing = setInterval(() => {
    setIndex(index + 1);
    if (index >= times.length - 1) stop();
  }, 900);
});

try {
  const response = await fetch("demo.json");
  if (!response.ok) throw new Error("Demo file is unavailable");
  demo = await response.json();
  reset();
} catch (error) {
  $("source").textContent = "Demo unavailable";
  $("file-status").textContent = error.message;
}

if (location.hostname === "127.0.0.1" && new URLSearchParams(location.search).get("local") === "1") {
  import("./local-sweeps.js");
}
