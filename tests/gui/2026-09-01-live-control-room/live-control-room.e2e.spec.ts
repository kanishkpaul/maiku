import { expect, test } from "@playwright/test";

test("the live control room adapts six participants and preserves the human write boundary", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bring different kinds of intelligence into one working room." })).toBeVisible();

  console.log("\n  1. Loading the prepared five through their real adapter/probe path.");
  const quickLoad = page.getByRole("button", { name: "quick-load 5" });
  if (await quickLoad.isEnabled()) await quickLoad.click();
  await expect(page.getByText("adapted + healthy")).toHaveCount(5, { timeout: 45_000 });

  console.log("  2. Adding the browser-backed human as the sixth participant.");
  await page.getByRole("button", { name: "04 Human desk" }).click();
  const addHuman = page.getByRole("button", { name: "add You" });
  if (await addHuman.isVisible()) await addHuman.click();
  await expect(page.getByText("You are present in the runtime.")).toBeVisible();

  console.log("  3. Starting the paced live case; this takes a little over two minutes.");
  await page.getByRole("button", { name: "run live case" }).click();
  await page.getByRole("button", { name: "04 Human desk" }).click();
  await expect(page.getByRole("button", { name: "Investigate and prepare a report" })).toBeVisible({ timeout: 45_000 });

  console.log("  4. The human chooses to investigate, then publishes the evidence report.");
  await page.getByRole("button", { name: "Investigate and prepare a report" }).click();
  await expect(page.getByRole("button", { name: "Publish the evidence report" })).toBeVisible({ timeout: 150_000 });
  await page.getByRole("button", { name: "Publish the evidence report" }).click();

  console.log("  5. The MCP write is paused for the final human approval.");
  await expect(page.getByRole("button", { name: "approve write" })).toBeVisible({ timeout: 45_000 });
  await page.getByRole("button", { name: "approve write" }).click();

  await page.getByRole("button", { name: "03 Event log" }).click();
  await expect(page.getByText("LIVE CASE COMPLETE", { exact: false })).toBeVisible({ timeout: 45_000 });
  console.log("  ✓ Real report write completed only after the browser human approved it.\n");
});
