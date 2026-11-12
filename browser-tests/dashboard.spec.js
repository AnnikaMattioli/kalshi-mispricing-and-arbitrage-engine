import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("./");
  await expect(page.locator("#source")).toHaveText("Synthetic demo");
});

test("scrubs replay, changes assumption and inspects residual exposure", async ({ page }) => {
  await expect(page.getByRole("heading", {name: "Replay timeline"})).toBeVisible();
  await expect(page.locator("#time-label")).toContainText("12:00:00 UTC");
  await expect(page.locator("#execution-note")).toContainText("All legs filled");
  await page.getByLabel("Execution assumption").selectOption("delayed_partial");
  await expect(page.locator("#execution-note")).toContainText("Residual exposure remains");
  await expect(page.locator("#legs tr")).toHaveCount(2);
  await expect(page.locator("#legs")).toContainText("partial");
  await page.getByRole("button", {name: "Next snapshot"}).click();
  await expect(page.locator("#time-label")).toContainText("12:00:05 UTC");
  await page.getByRole("button", {name: "Play", exact: true}).click();
  await expect(page.locator("#time-label")).toContainText("12:00:15 UTC");
});

test("plots accessible model charts and calibration counts", async ({ page }) => {
  await expect(page.getByRole("img", {name: /Brier score bars/})).toBeVisible();
  await expect(page.getByRole("img", {name: /Calibration scatter/})).toBeVisible();
  await page.getByText("View calibration table").click();
  await expect(page.locator("#calibration-table tbody tr").first()).toBeVisible();
  await expect(page.locator("#model-note")).toContainText("150 holdout rows");
});

test("opens a local report without a network upload and restores the demo", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => requests.push(request.method()));
  const calibration = [{lower: 0, upper: 1, n: 1, mean_probability: .6, observed_frequency: 1}];
  const data = {train_games: 40, holdout_games: 1, depth_matched_games: 0,
    metrics: {model: {brier: .16, calibration}, midpoint: {brier: .25, calibration}}};
  await page.getByLabel("Open report").setInputFiles({
    name: "local-study.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(data)),
  });
  await expect(page.locator("#model-source")).toHaveText("Local model report");
  await expect(page.locator("#model-note")).toContainText("1 holdout rows");
  expect(requests).toEqual([]);
  await page.getByRole("button", {name: "Reset demo"}).click();
  await expect(page.locator("#model-source")).toHaveText("Synthetic holdout");
});

test("rejects a malformed report and fits a narrow viewport", async ({ page }) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.getByLabel("Open report").setInputFiles({
    name: "invalid.json", mimeType: "application/json", buffer: Buffer.from("{"),
  });
  await expect(page.locator("#file-status")).toContainText("Could not open report");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test("local sweep panel refreshes and exposes stale and failed captures", async ({ page }) => {
  test.skip(Boolean(process.env.DASHBOARD_URL), "Local dashboard uses a loopback-only route");
  let sweeps = [{
    file: "saved.jsonl", series: "KXHIGHNY", status: "complete", stale: true,
    captured_at: "2026-11-10T20:55:00Z", age_seconds: 3600,
    counts: {books_received: 6, markets_discovered: 6},
    events: [{ticker: "KXHIGHNY-DEMO", decisions: {no_edge: 5}, oldest_priced_quote_seconds: 2.5}],
  }];
  await page.route("**/api/sweeps", (route) => route.fulfill({
    json: {checked_at: "2026-11-10T21:55:00Z", sweeps},
  }));
  await expect(page.getByRole("heading", {name: "Saved scanner sweeps"})).toBeHidden();
  await page.goto("./?local=1");
  await expect(page.locator("#sweep-results")).toContainText("Stale");
  await expect(page.locator("#sweep-results")).toContainText("2.50 s");
  sweeps = [{...sweeps[0], status: "failed", counts: {request_failures: 2}, events: []}];
  await page.getByRole("button", {name: "Refresh sweeps"}).click();
  await expect(page.locator("#sweep-results")).toContainText("Sweep failed");
  await expect(page.locator("#sweep-results")).toContainText("2 request failures");
});
