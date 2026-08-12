import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import type { BacktestResult } from "../src/api/types";
import { fixedBacktestResult } from "../src/test/fixture";

interface FixtureState {
  hasRun: boolean;
  hasPreset: boolean;
  backtestRequests: number;
  savedPresetPayload: unknown;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json; charset=utf-8",
    body: JSON.stringify(body),
  });
}

async function installApiFixture(
  page: Page,
  backtestResult = fixedBacktestResult,
): Promise<FixtureState> {
  const state: FixtureState = {
    hasRun: false,
    hasPreset: false,
    backtestRequests: 0,
    savedPresetPayload: null,
  };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/runtime") {
      return json(route, {
        mode: "DESKTOP",
        authenticated: true,
        pairing_required: false,
        lan_url: null,
        pairing_code: null,
      });
    }
    if (url.pathname === "/api/settings") {
      return json(
        route,
        request.method() === "PUT"
          ? request.postDataJSON()
          : { theme: "SYSTEM", lan_enabled: false },
      );
    }
    if (url.pathname.startsWith("/api/symbols/")) {
      const requested = decodeURIComponent(url.pathname.split("/").at(-1) ?? "0700.HK");
      if (!/^\d{1,5}(?:\.HK)?$/i.test(requested)) {
        return json(
          route,
          {
            error: {
              code: "INVALID_SYMBOL",
              message: "请输入有效的港股代码，例如 0700.HK。",
              field: "symbol",
              details: {},
            },
          },
          422,
        );
      }
      const digits = requested.replace(/\.HK$/i, "").replace(/^0+/, "") || "0";
      const normalized = `${digits.padStart(4, "0")}.HK`;
      return json(route, {
        symbol: {
          normalized_symbol: normalized,
          exchange: "HKEX",
          currency: "HKD",
          display_name: null,
          local_alias: null,
        },
        board_lot: {
          lot_size: normalized === "2800.HK" ? 500 : 100,
          source: "AUTO",
          verified_at: fixedBacktestResult.created_at_utc,
          confirmed: true,
        },
        board_lot_requires_confirmation: false,
        provider: "Fixed E2E provider",
      });
    }
    if (url.pathname === "/api/backtests" && request.method() === "POST") {
      state.backtestRequests += 1;
      const input = request.postDataJSON() as {
        symbol: string;
        benchmark_symbol: string;
        initial_capital: number;
      };
      if (input.symbol === "INVALID") {
        return json(
          route,
          {
            error: {
              code: "INVALID_SYMBOL",
              message: "请输入有效的港股代码，例如 0700.HK。",
              field: "symbol",
              details: {},
            },
          },
          422,
        );
      }
      if (input.symbol === "9998.HK") {
        return json(
          route,
          {
            error: {
              code: "PROVIDER_ERROR",
              message: "无法获取 9998.HK 的行情，请稍后重试。",
              field: "symbol",
              details: {},
            },
          },
          502,
        );
      }
      if (input.benchmark_symbol === "9999.HK") {
        return json(
          route,
          {
            error: {
              code: "DATA_NOT_FOUND",
              message: "无法获取 9999.HK 在该区间的基准数据。",
              field: "benchmark_symbol",
              details: {},
            },
          },
          502,
        );
      }
      if (input.initial_capital === 1) {
        return json(
          route,
          {
            error: {
              code: "INSUFFICIENT_CAPITAL",
              message: "初始资金不足以买入一手 0700.HK。",
              field: "initial_capital",
              details: { board_lot: 100 },
            },
          },
          422,
        );
      }
      state.hasRun = true;
      return json(route, backtestResult);
    }
    if (url.pathname === "/api/history") {
      return json(
        route,
        state.hasRun
          ? [
              {
                run_id: backtestResult.run_id,
                symbol: "0700.HK",
                benchmark: "2800.HK",
                created_at: backtestResult.created_at_utc,
                date_range: backtestResult.date_range,
                strategy_metrics: backtestResult.strategy_metrics,
                benchmark_metrics: backtestResult.benchmark_metrics,
                trade_count: backtestResult.trades.length,
              },
            ]
          : [],
      );
    }
    if (url.pathname === "/api/recent-symbols") return json(route, ["0700.HK", "9988.HK"]);
    if (url.pathname === "/api/presets" && request.method() === "GET") {
      return json(
        route,
        state.hasPreset
          ? [
              {
                id: 1,
                name: "腾讯 SMA 20/60",
                payload: state.savedPresetPayload,
                updated_at: fixedBacktestResult.created_at_utc,
              },
            ]
          : [],
      );
    }
    if (url.pathname === "/api/presets" && request.method() === "POST") {
      state.hasPreset = true;
      const input = request.postDataJSON() as { name: string; payload: unknown };
      state.savedPresetPayload = input.payload;
      return json(route, { id: 1, ...input, updated_at: fixedBacktestResult.created_at_utc }, 201);
    }
    if (url.pathname.endsWith("/prepare") && request.method() === "POST") {
      return json(route, {
        run_id: backtestResult.run_id,
        generated_at_utc: backtestResult.created_at_utc,
        files: {
          "report.html": 1200,
          "trades.csv": 600,
          "manifest.json": 800,
          "bundle.zip": 1800,
        },
      });
    }
    if (url.pathname === `/api/backtests/${backtestResult.run_id}`) {
      return json(route, backtestResult);
    }
    return json(route, { error: { code: "NOT_FOUND", message: "未找到接口。" } }, 404);
  });
  return state;
}

async function runDefaultBacktest(page: Page) {
  await page.getByRole("button", { name: /运行回测/ }).click();
  await expect(page.getByText("回测概览")).toBeVisible();
}

function resultWithTradeCount(count: number): BacktestResult {
  const tradeTemplate = fixedBacktestResult.trades[0];
  return {
    ...fixedBacktestResult,
    trades: Array.from({ length: count }, (_, index) => ({
      ...tradeTemplate,
      trade_id: index + 1,
      net_pnl: tradeTemplate.net_pnl - index * 10,
    })),
  };
}

async function alignTradeSectionBelowNavigation(page: Page) {
  await page.evaluate(() => {
    const section = document.querySelector('[data-testid="trade-table-shell"]');
    const navigation = document.querySelector(".result-tabs > .ant-tabs-nav");
    if (!(section instanceof HTMLElement) || !(navigation instanceof HTMLElement)) return;
    const navigationBottom = navigation.getBoundingClientRect().bottom;
    const target = section.getBoundingClientRect().top + window.scrollY - navigationBottom - 16;
    window.scrollTo({ top: Math.max(0, target), behavior: "auto" });
  });
}

async function tradeGeometry(page: Page) {
  return page.evaluate(() => {
    const shell = document.querySelector('[data-testid="trade-table-shell"]');
    const details = (element: Element | null) => {
      if (!(element instanceof HTMLElement)) throw new Error("Expected trade table element");
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        left: rect.left,
        width: rect.width,
        height: rect.height,
        position: style.position,
        zIndex: style.zIndex,
        overflowX: style.overflowX,
        overflowY: style.overflowY,
        backgroundColor: style.backgroundColor,
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
        scrollTop: element.scrollTop,
      };
    };
    const tableBody = shell?.querySelector(".ant-table-body") ?? null;
    if (!(tableBody instanceof HTMLElement)) throw new Error("Expected a vertical table body");
    const bodyRect = tableBody.getBoundingClientRect();
    const visibleRow = Array.from(
      shell?.querySelectorAll(".ant-table-tbody > tr.ant-table-row") ?? [],
    )
      .map((row) => row.getBoundingClientRect())
      .find((rect) => rect.bottom > bodyRect.top && rect.top < bodyRect.bottom);
    if (!visibleRow) throw new Error("Expected a visible trade row");
    return {
      appHeader: details(document.querySelector(".product-header")),
      resultNavigation: details(document.querySelector(".result-tabs > .ant-tabs-nav")),
      tableHeader: details(shell?.querySelector(".ant-table-header") ?? null),
      tableBody: details(tableBody),
      firstVisibleRow: {
        top: visibleRow.top,
        bottom: visibleRow.bottom,
        visibleTop: Math.max(visibleRow.top, bodyRect.top),
      },
      viewport: {
        width: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        scrollY: window.scrollY,
      },
    };
  });
}

async function expectTradeLayersSeparated(page: Page) {
  const geometry = await tradeGeometry(page);
  expect(geometry.appHeader.top).toBeGreaterThanOrEqual(-1);
  expect(geometry.appHeader.top).toBeLessThanOrEqual(1);
  expect(geometry.appHeader.bottom).toBeLessThanOrEqual(geometry.resultNavigation.top + 1);
  expect(geometry.resultNavigation.bottom).toBeLessThanOrEqual(geometry.tableHeader.top + 1);
  expect(geometry.tableHeader.bottom).toBeLessThanOrEqual(geometry.firstVisibleRow.visibleTop + 1);
  expect(geometry.tableBody.scrollHeight).toBeGreaterThan(geometry.tableBody.clientHeight);
  expect(["auto", "scroll"]).toContain(geometry.tableBody.overflowY);
  expect(geometry.tableHeader.position).not.toBe("sticky");
  expect(geometry.tableHeader.backgroundColor).not.toBe("rgba(0, 0, 0, 0)");
  expect(Number(geometry.appHeader.zIndex)).toBe(40);
  expect(Number(geometry.resultNavigation.zIndex)).toBe(30);
  expect(Number(geometry.tableHeader.zIndex)).toBe(20);
  expect(geometry.viewport.documentWidth).toBeLessThanOrEqual(geometry.viewport.width);
}

async function scrollTradeRowToTop(page: Page, tradeId: number) {
  const row = page.locator(`[data-testid="trade-table-shell"] tr[data-row-key="${tradeId}"]`);
  await expect(row).toBeAttached();
  await row.evaluate((element) => {
    const body = element.closest(".ant-table-body");
    if (!(body instanceof HTMLElement) || !(element instanceof HTMLElement)) {
      throw new Error("Expected a scrollable trade table row");
    }
    body.scrollTop = element.offsetTop;
  });
  await expectTradeLayersSeparated(page);
}

test("desktop fixed-fixture product flow covers research, history, preset, theme and export", async ({
  page,
}) => {
  const readmeScreenshot = process.env.QUANTLAB_README_SCREENSHOT;
  if (readmeScreenshot) {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.emulateMedia({ colorScheme: "light" });
  }
  const state = await installApiFixture(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "QuantLab" })).toBeVisible();
  await expect(page.getByLabel("港股代码")).toHaveValue("0700.HK");
  if (readmeScreenshot) {
    await page.getByLabel("港股代码").focus();
    await page.getByLabel("港股代码").blur();
    await page.getByLabel("比较基准").focus();
    await page.getByLabel("比较基准").blur();
    await expect(page.getByText("自动获取")).toHaveCount(2);
  }
  await runDefaultBacktest(page);
  expect(state.backtestRequests).toBe(1);

  if (readmeScreenshot) {
    await page.getByRole("tab", { name: "净值与回撤" }).click();
    await expect(page.getByRole("img", { name: "策略与买入持有基准净值对比图" })).toBeVisible();
    await expect(page.getByRole("img", { name: "策略回撤曲线" })).toBeVisible();
    await page.waitForTimeout(2500);
    await page.locator(".parameter-sider").evaluate((element) => element.scrollTo(0, 0));
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: path.resolve(process.cwd(), readmeScreenshot),
      animations: "disabled",
      fullPage: false,
    });
  }

  await page.getByRole("tab", { name: "行情与信号" }).click();
  await expect(page.getByRole("img", { name: "调整后价格、双均线与交易标记图" })).toBeVisible();
  await page.getByRole("tab", { name: "净值与回撤" }).click();
  await expect(page.getByRole("img", { name: "策略与买入持有基准净值对比图" })).toBeVisible();
  await page.getByRole("tab", { name: "交易记录" }).click();
  await expect(page.getByRole("heading", { name: "交易记录" })).toBeVisible();

  await page.getByRole("button", { name: "外观设置" }).click();
  await page.getByRole("menuitem", { name: /深色/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.getByRole("button", { name: /预设/ }).click();
  await page.getByLabel("预设名称").fill("腾讯 SMA 20/60");
  await page.getByRole("button", { name: /保存当前参数/ }).click();
  await page
    .getByRole("dialog", { name: "研究预设" })
    .getByRole("button", { name: "关闭" })
    .click();
  await page.getByRole("button", { name: /历史/ }).click();
  await expect(
    page.getByRole("dialog", { name: "本地运行历史" }).getByText("0700.HK"),
  ).toBeVisible();
  await page
    .getByRole("dialog", { name: "本地运行历史" })
    .getByRole("button", { name: "关闭" })
    .click();

  await page.getByRole("tab", { name: "导出" }).click();
  await page.getByRole("button", { name: /准备导出文件/ }).click();
  await expect(page.getByText("全部结果 ZIP")).toBeVisible();
  expect(state.backtestRequests).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

for (const viewport of [
  { width: 390, height: 844 },
  { width: 412, height: 915 },
]) {
  test(`mobile ${viewport.width} uses drawers, one chart and trade cards without page overflow`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const state = await installApiFixture(page);
    await page.goto("/");
    await page.getByRole("button", { name: "参数" }).click();
    const parameters = page.getByRole("dialog", { name: "研究参数" });
    await expect(parameters).toBeVisible();
    await parameters.getByRole("button", { name: /运行回测/ }).click();
    await expect(parameters).toBeHidden();
    await expect(page.getByText("回测概览")).toBeVisible();

    await page.getByRole("tab", { name: "图表" }).click();
    await expect(page.getByRole("img", { name: "策略与买入持有基准净值对比图" })).toBeVisible();
    await page.getByText("回撤", { exact: true }).click();
    await expect(page.getByRole("img", { name: "策略回撤曲线" })).toBeVisible();
    await page.getByRole("tab", { name: "交易记录" }).click();
    await expect(page.getByText("#1 · 已平仓")).toBeVisible();

    await page.getByRole("button", { name: "历史" }).click();
    await expect(page.getByRole("dialog", { name: "本地运行历史" })).toBeVisible();
    await page
      .getByRole("dialog", { name: "本地运行历史" })
      .getByRole("button", { name: "关闭" })
      .click();
    await page.getByRole("button", { name: "更多" }).click();
    await page.getByRole("menuitem", { name: /外观：深色/ }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    expect(state.backtestRequests).toBe(1);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });
}

test("SYSTEM follows live OS changes while explicit DARK remains stable", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await installApiFixture(page);
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await page.getByRole("button", { name: "外观设置" }).click();
  await page.getByRole("menuitem", { name: /深色/ }).click();
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.getByRole("button", { name: "外观设置" }).click();
  await page.getByRole("menuitem", { name: /跟随系统/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("validation errors identify the field in Chinese without traceback", async ({ page }) => {
  const state = await installApiFixture(page);
  await page.goto("/");
  const parameterForm = page.getByRole("form", { name: "港股回测参数" });
  const workspace = page.getByRole("main");

  await page.getByLabel("短均线").fill("60");
  await page.getByLabel("长均线").fill("20");
  await page.getByRole("button", { name: /运行回测/ }).click();
  await expect(page.getByText("长均线必须大于短均线")).toBeVisible();
  expect(state.backtestRequests).toBe(0);

  await page.getByLabel("短均线").fill("20");
  await page.getByLabel("长均线").fill("60");
  await page.getByLabel(/每手股数/).fill("");
  await page.getByRole("button", { name: /运行回测/ }).click();
  await expect(page.getByText("请确认标的每手股数")).toBeVisible();
  expect(state.backtestRequests).toBe(0);

  await page.getByLabel(/每手股数/).fill("100");
  await page.getByLabel("港股代码").fill("INVALID");
  await page.getByRole("button", { name: /运行回测/ }).click();
  await expect(parameterForm.getByText("请输入有效的港股代码，例如 0700.HK。")).toBeVisible();
  await expect(page.getByLabel("港股代码")).toHaveAttribute("aria-invalid", "true");

  await page.getByLabel("港股代码").fill("9998.HK");
  await page.getByRole("button", { name: /运行回测/ }).click();
  await expect(workspace.getByText("无法获取 9998.HK 的行情，请稍后重试。")).toBeVisible();
  await expect(page.getByLabel("港股代码")).toBeFocused();

  await page.getByLabel("港股代码").fill("0700.HK");
  await page.getByLabel("初始资金").fill("1");
  await page.getByRole("button", { name: /运行回测/ }).click();
  await expect(workspace.getByText("初始资金不足以买入一手 0700.HK。")).toBeVisible();
  await expect(page.getByLabel("初始资金")).toBeFocused();

  await page.getByLabel("初始资金").fill("100000");
  await page.getByLabel("比较基准").fill("9999.HK");
  await page.getByRole("button", { name: /运行回测/ }).click();
  await expect(workspace.getByText("无法获取 9999.HK 在该区间的基准数据。")).toBeVisible();
  await expect(page.getByLabel("比较基准")).toBeFocused();
  await expect(page.locator("body")).not.toContainText("Traceback");
});

test("trade table owns its vertical scroll without overlapping sticky navigation", async ({
  page,
}) => {
  const screenshotDirectory = path.resolve(process.cwd(), "..", "artifacts", "trade-table-scroll");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.emulateMedia({ colorScheme: "light" });
  await installApiFixture(page, resultWithTradeCount(55));
  await page.goto("/");
  await runDefaultBacktest(page);
  await page.getByRole("tab", { name: "交易记录" }).click();
  await expect(page.getByRole("heading", { name: "交易记录" })).toBeVisible();
  await alignTradeSectionBelowNavigation(page);

  const tableBody = page.locator('[data-testid="trade-table-shell"] .ant-table-body');
  await expectTradeLayersSeparated(page);
  await writeFile(
    path.join(screenshotDirectory, "geometry-1366-light.json"),
    `${JSON.stringify(await tradeGeometry(page), null, 2)}\n`,
    "utf8",
  );
  await page.screenshot({ path: path.join(screenshotDirectory, "01-table-top-light.png") });
  await page.screenshot({ path: path.join(screenshotDirectory, "07-desktop-1366-light.png") });

  await scrollTradeRowToTop(page, 1);
  await scrollTradeRowToTop(page, 5);
  await scrollTradeRowToTop(page, 10);
  await tableBody.evaluate((element) => {
    element.scrollTop = 0;
  });

  const pageScrollBeforeWheel = await page.evaluate(() => window.scrollY);
  await tableBody.hover();
  await page.mouse.wheel(0, 480);
  await expect.poll(() => tableBody.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(pageScrollBeforeWheel);
  await expectTradeLayersSeparated(page);
  await page.screenshot({ path: path.join(screenshotDirectory, "02-table-middle-light.png") });
  await page.screenshot({ path: path.join(screenshotDirectory, "06-light-middle.png") });

  await tableBody.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expectTradeLayersSeparated(page);
  await page.screenshot({ path: path.join(screenshotDirectory, "03-table-bottom-light.png") });

  const pageScrollAtBoundary = await page.evaluate(() => window.scrollY);
  await tableBody.hover();
  await page.mouse.wheel(0, 480);
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(pageScrollAtBoundary);
  await alignTradeSectionBelowNavigation(page);

  await page.locator(".ant-pagination-item-3").click();
  await tableBody.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(page.locator('tr[data-row-key="55"]')).toBeVisible();
  await expectTradeLayersSeparated(page);
  await page.locator(".ant-pagination-item-1").click();

  await tableBody.evaluate((element) => {
    element.scrollTop = Math.floor(element.scrollHeight / 2);
  });
  await page.getByRole("columnheader", { name: /净损益/ }).click();
  await expect.poll(() => tableBody.evaluate((element) => element.scrollTop)).toBe(0);

  await tableBody.evaluate((element) => {
    element.scrollTop = Math.floor(element.scrollHeight / 2);
  });
  await page.locator(".ant-pagination-next button").click();
  await expect.poll(() => tableBody.evaluate((element) => element.scrollTop)).toBe(0);
  await page.locator(".ant-pagination-prev button").click();

  await tableBody.evaluate((element) => {
    element.scrollTop = Math.floor(element.scrollHeight / 2);
  });
  await page.locator(".trade-table-shell .ant-pagination-options-size-changer").click();
  await expect(page.getByRole("option", { name: /20/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /50/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /100/ })).toBeVisible();
  await page.getByRole("option", { name: /50/ }).click();
  await expect.poll(() => tableBody.evaluate((element) => element.scrollTop)).toBe(0);
  await expect(page.locator(".ant-table-tbody > tr.ant-table-row")).toHaveCount(50);

  await page.locator(".ant-table-row-expand-icon").first().click();
  await expect(page.getByText("买入佣金").first()).toBeVisible();
  await expectTradeLayersSeparated(page);
  await page.screenshot({ path: path.join(screenshotDirectory, "04-expanded-costs-light.png") });

  await page.setViewportSize({ width: 768, height: 1024 });
  await alignTradeSectionBelowNavigation(page);
  await expectTradeLayersSeparated(page);

  await page.setViewportSize({ width: 1600, height: 900 });
  await alignTradeSectionBelowNavigation(page);
  await expectTradeLayersSeparated(page);
  await writeFile(
    path.join(screenshotDirectory, "geometry-1600-light.json"),
    `${JSON.stringify(await tradeGeometry(page), null, 2)}\n`,
    "utf8",
  );

  await page.getByRole("button", { name: "外观设置" }).click();
  await page.getByRole("menuitem", { name: /深色/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.setViewportSize({ width: 1920, height: 1080 });
  await alignTradeSectionBelowNavigation(page);
  await tableBody.evaluate((element) => {
    element.scrollTop = Math.floor(element.scrollHeight / 2);
  });
  await expectTradeLayersSeparated(page);
  await writeFile(
    path.join(screenshotDirectory, "geometry-1920-dark.json"),
    `${JSON.stringify(await tradeGeometry(page), null, 2)}\n`,
    "utf8",
  );
  await page.screenshot({ path: path.join(screenshotDirectory, "05-dark-middle.png") });
  await page.screenshot({ path: path.join(screenshotDirectory, "08-desktop-1920-dark.png") });
});
