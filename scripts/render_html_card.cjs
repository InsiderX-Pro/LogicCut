#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

function loadPlaywright() {
  const candidates = [
    process.env.LOGICCUT_PLAYWRIGHT_MODULE,
    path.resolve(__dirname, "../node_modules/playwright"),
    path.resolve(__dirname, "../third_party/OmniVoice-Studio/node_modules/playwright"),
    "playwright",
  ].filter(Boolean);

  const errors = [];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      errors.push(`${candidate}: ${error.message}`);
    }
  }
  throw new Error(`Unable to load playwright. Tried: ${errors.join(" | ")}`);
}

function chromiumExecutable() {
  const candidates = [
    process.env.LOGICCUT_CHROMIUM_EXECUTABLE,
    "/workspace/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
    "/workspace/.cache/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell",
  ].filter(Boolean);
  return candidates.find((item) => fs.existsSync(item));
}

async function main() {
  const [htmlPath, outputPath, widthRaw, heightRaw] = process.argv.slice(2);
  if (!htmlPath || !outputPath || !widthRaw || !heightRaw) {
    throw new Error("Usage: render_html_card.cjs <html> <output.png> <width> <height>");
  }

  const width = Number.parseInt(widthRaw, 10);
  const height = Number.parseInt(heightRaw, 10);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new Error(`Invalid viewport: ${widthRaw}x${heightRaw}`);
  }

  const { chromium } = loadPlaywright();
  const launchOptions = {
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  };
  const executablePath = chromiumExecutable();
  if (executablePath) {
    launchOptions.executablePath = executablePath;
  }

  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(path.resolve(htmlPath)).href, { waitUntil: "networkidle" });
    await page.screenshot({ path: path.resolve(outputPath), type: "png", fullPage: false });
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
