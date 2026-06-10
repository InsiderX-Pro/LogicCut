#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) continue;
    const name = key.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[name] = true;
    } else {
      args[name] = next;
      i += 1;
    }
  }
  return args;
}

function loadPlaywright() {
  const candidates = [
    "playwright",
    path.resolve(__dirname, "../third_party/OmniVoice-Studio/node_modules/.bun/playwright@1.60.0/node_modules/playwright"),
    path.resolve(__dirname, "../third_party/OmniVoice-Studio/node_modules/playwright"),
  ];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (_error) {
      // Try the next known location.
    }
  }
  throw new Error("Playwright is not installed. Run scripts/setup_node_tools.sh or install playwright.");
}

function detectPlatform(url) {
  const lower = String(url).toLowerCase();
  if (lower.includes("youtube.com") || lower.includes("youtu.be")) return "youtube";
  if (lower.includes("bilibili.com") || lower.includes("b23.tv")) return "bilibili";
  return "unknown";
}

function cookieDomainForUrl(targetUrl) {
  const hostname = new URL(targetUrl).hostname;
  if (hostname.endsWith("bilibili.com")) return ".bilibili.com";
  if (hostname.endsWith("youtube.com")) return ".youtube.com";
  return hostname;
}

function parseCookieHeader(text, targetUrl) {
  const header = text.trim().replace(/^cookie:\s*/i, "");
  if (!header || !header.includes("=")) return [];
  const domain = cookieDomainForUrl(targetUrl);
  return header
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const index = item.indexOf("=");
      if (index <= 0) return null;
      return {
        domain,
        path: "/",
        secure: true,
        sameSite: "Lax",
        name: item.slice(0, index).trim(),
        value: item.slice(index + 1).trim(),
      };
    })
    .filter(Boolean);
}

function parseCookiesFile(filePath, targetUrl) {
  if (!filePath || !fs.existsSync(filePath)) return [];
  const text = fs.readFileSync(filePath, "utf8");
  const trimmed = text.trim();
  if (!trimmed) return [];

  if (!trimmed.includes("\t") && trimmed.includes(";")) {
    return parseCookieHeader(trimmed, targetUrl);
  }

  return text
    .split(/\r?\n/)
    .map((line) => (line.startsWith("#HttpOnly_") ? line.replace("#HttpOnly_", "") : line))
    .filter((line) => line.trim() && !line.startsWith("#"))
    .map((line) => line.split("\t"))
    .filter((parts) => parts.length >= 7)
    .map((parts) => ({
      domain: parts[0],
      path: parts[2] || "/",
      secure: String(parts[3]).toUpperCase() === "TRUE",
      expires: Number(parts[4]) || -1,
      name: parts[5],
      value: parts.slice(6).join("\t"),
      sameSite: "Lax",
    }));
}

async function bestEffortClick(page, patterns) {
  for (const pattern of patterns) {
    try {
      const locator = page.getByText(pattern, { exact: false }).first();
      if ((await locator.count()) > 0) {
        await locator.click({ timeout: 1500 });
        await page.waitForTimeout(500);
        return true;
      }
    } catch (_error) {
      // Ignore pop-up mismatches.
    }
  }
  return false;
}

async function closeKnownOverlays(page) {
  await bestEffortClick(page, [
    "Accept all",
    "I agree",
    "同意",
    "接受",
    "知道了",
    "我知道了",
    "Got it",
  ]);
  const selectors = [
    ".bili-mini-close-icon",
    ".bili-modal-close",
    ".login-tip-close",
    ".adblock-tips-close",
    "button[aria-label='Close']",
    "button[aria-label='关闭']",
  ];
  for (const selector of selectors) {
    try {
      const locator = page.locator(selector).first();
      if ((await locator.count()) > 0) {
        await locator.click({ timeout: 1000 });
        await page.waitForTimeout(300);
      }
    } catch (_error) {
      // Not every page has every overlay.
    }
  }
}

async function findCommentSelector(page, platform) {
  const selectors =
    platform === "youtube"
      ? ["#comments", "ytd-comments", "ytd-item-section-renderer#sections"]
      : [
          ".reply-warp",
          ".comment-container",
          ".reply-list",
          "bili-comments",
          "#comment",
          ".bili-comment-container",
        ];
  return await page.evaluate((candidateSelectors) => {
    for (const selector of candidateSelectors) {
      const element = document.querySelector(selector);
      if (!element) continue;
      const rect = element.getBoundingClientRect();
      if (rect.height > 80 || element.scrollHeight > 80) {
        element.scrollIntoView({ block: "start", behavior: "instant" });
        return selector;
      }
    }
    return "";
  }, selectors);
}

async function scrollToComments(page, platform) {
  let selector = "";
  for (let i = 0; i < 10; i += 1) {
    selector = await findCommentSelector(page, platform);
    if (selector) break;
    await page.evaluate(() => window.scrollBy(0, Math.floor(window.innerHeight * 0.85)));
    await page.waitForTimeout(900);
    await closeKnownOverlays(page);
  }
  if (!selector) {
    await page.evaluate(() => window.scrollBy(0, Math.floor(window.innerHeight * 2.4)));
    await page.waitForTimeout(900);
  }
  return selector;
}

async function detectLoginGate(page, platform) {
  return await page.evaluate((currentPlatform) => {
    const text = document.body ? document.body.innerText || "" : "";
    const patterns =
      currentPlatform === "bilibili"
        ? [/登录后查看\s*\d+\s*条评论/, /登录后查看更多评论/, /登录后查看评论/]
        : [/Sign in to confirm/, /Sign in to view comments/, /登录后即可查看评论/];
    return patterns.some((pattern) => pattern.test(text));
  }, platform);
}

function commentItemSelectors(platform) {
  if (platform === "youtube") {
    return [
      "ytd-comment-thread-renderer",
      "ytd-comment-view-model",
      "#comments #contents > ytd-comment-thread-renderer",
    ];
  }
  return [
    ".reply-item",
    ".root-reply-container",
    ".reply-card",
    ".bili-comment-item",
    ".comment-item",
    ".reply-list .list-item",
  ];
}

async function visibleCommentItemHandles(page, platform) {
  const selectors = commentItemSelectors(platform);
  return await page.evaluateHandle((candidateSelectors) => {
    const seen = new Set();
    const items = [];
    for (const selector of candidateSelectors) {
      for (const element of document.querySelectorAll(selector)) {
        if (seen.has(element)) continue;
        seen.add(element);
        const rect = element.getBoundingClientRect();
        const text = (element.innerText || "").trim();
        if (rect.width < 240 || rect.height < 56 || text.length < 8) continue;
        items.push(element);
      }
      if (items.length > 0) break;
    }
    return items;
  }, selectors);
}

async function collectBilibiliShadowCommentClips(page, count) {
  return await page.evaluate((maxCount) => {
    const readText = (element) => (element.innerText || element.textContent || "").trim().replace(/\s+/g, " ");
    const deepElements = (root, depth = 0, result = []) => {
      if (!root || depth > 8) return result;
      const children =
        root instanceof ShadowRoot || root instanceof Document
          ? Array.from(root.querySelectorAll("*"))
          : Array.from(root.children || []);
      for (const element of children) {
        result.push({ element, depth });
        if (element.shadowRoot) {
          deepElements(element.shadowRoot, depth + 1, result);
        }
      }
      return result;
    };
    const all = deepElements(document)
      .map(({ element, depth }) => {
        const rect = element.getBoundingClientRect();
        return {
          element,
          depth,
          tag: element.tagName.toLowerCase(),
          id: element.id || "",
          text: readText(element),
          rect: {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            pageX: rect.x + window.scrollX,
            pageY: rect.y + window.scrollY,
          },
        };
      })
      .filter((item) => item.rect.width > 0 && item.rect.height > 0);

    const topLevelContents = all
      .filter((item) => {
        if (item.id !== "contents" || item.tag !== "p") return false;
        if (item.text.length < 4 || item.text.length > 420) return false;
        if (item.text.includes("@font-face") || item.text.includes("登录后查看")) return false;
        const x = item.rect.x;
        return x >= 130 && x <= 190;
      })
      .sort((a, b) => a.rect.pageY - b.rect.pageY);

    const items = [];
    const seen = new Set();
    for (const content of topLevelContents) {
      if (items.length >= maxCount) break;
      const key = content.text.slice(0, 100);
      if (seen.has(key)) continue;
      seen.add(key);
      const topLimit = content.rect.y - 90;
      const bottomLimit = content.rect.y + Math.max(170, content.rect.height + 120);
      const author = all
        .filter((item) => {
          if (item.id !== "user-name" && item.id !== "info") return false;
          if (item.text.length < 1 || item.text.length > 32) return false;
          return item.rect.y >= topLimit && item.rect.y <= content.rect.y + 10 && item.rect.x >= 130 && item.rect.x <= 230;
        })
        .sort((a, b) => Math.abs(a.rect.y - content.rect.y) - Math.abs(b.rect.y - content.rect.y))[0];
      const pubdate = all
        .filter((item) => {
          if (item.id !== "pubdate") return false;
          return item.rect.y >= content.rect.y && item.rect.y <= bottomLimit && item.rect.x >= 130 && item.rect.x <= 240;
        })
        .sort((a, b) => a.rect.y - b.rect.y)[0];
      const topY = Math.max(0, Math.min(author?.rect.pageY ?? content.rect.pageY, content.rect.pageY) - 18);
      const bottomY = Math.max(
        content.rect.pageY + content.rect.height + 42,
        (pubdate?.rect.pageY ?? content.rect.pageY + content.rect.height) + (pubdate?.rect.height ?? 20) + 20,
      );
      const clipX = Math.max(0, content.rect.pageX - 80);
      const clipWidth = Math.min(760, Math.max(620, document.documentElement.clientWidth - clipX - 32));
      const clipHeight = Math.min(360, Math.max(112, bottomY - topY));
      items.push({
        author: author?.text || "",
        visible_text: content.text,
        like_text: "",
        reply_text: "",
        rect: {
          x: Math.round(clipX),
          y: Math.round(topY),
          width: Math.round(clipWidth),
          height: Math.round(clipHeight),
        },
      });
    }
    return items;
  }, count);
}

async function captureBilibiliShadowVisualItems(page, outputDir, count) {
  const visualDir = path.join(outputDir, "comment_items");
  fs.mkdirSync(visualDir, { recursive: true });
  const visualItems = [];
  const seenText = new Set();
  let scrollAttempts = 0;
  while (visualItems.length < count && scrollAttempts < count * 3) {
    const clips = await collectBilibiliShadowCommentClips(page, count * 2);
    for (const clipData of clips) {
      if (visualItems.length >= count) break;
      const key = String(clipData.visible_text || "").slice(0, 120);
      if (!key || seenText.has(key)) continue;
      seenText.add(key);
      const filename = `${String(visualItems.length + 1).padStart(3, "0")}.png`;
      await page.evaluate((pageY) => {
        window.scrollTo(0, Math.max(0, Math.round(pageY - 90)));
      }, clipData.rect.y);
      await page.waitForTimeout(250);
      const scrollY = await page.evaluate(() => window.scrollY);
      const viewport = await page.viewportSize();
      const viewportClip = {
        x: Math.max(0, Math.round(clipData.rect.x)),
        y: Math.max(0, Math.round(clipData.rect.y - scrollY)),
        width: Math.max(1, Math.round(clipData.rect.width)),
        height: Math.max(1, Math.round(clipData.rect.height)),
      };
      viewportClip.width = Math.min(viewportClip.width, Math.max(1, viewport.width - viewportClip.x - 4));
      viewportClip.height = Math.min(viewportClip.height, Math.max(1, viewport.height - viewportClip.y - 4));
      await page.screenshot({
        path: path.join(visualDir, filename),
        clip: viewportClip,
      });
      visualItems.push({
        id: `bilibili_shadow_${String(visualItems.length + 1).padStart(3, "0")}`,
        kind: "comment_dom_clip",
        platform: "bilibili",
        path: `comment_items/${filename}`,
        author: clipData.author,
        visible_text: clipData.visible_text,
        like_text: clipData.like_text,
        reply_text: clipData.reply_text,
        rect: { ...clipData.rect, viewport_clip: viewportClip },
      });
    }
    if (visualItems.length >= count) break;
    await page.mouse.wheel(0, Math.floor((await page.viewportSize()).height * 0.82));
    await page.waitForTimeout(1000);
    scrollAttempts += 1;
  }
  return visualItems;
}

async function extractCommentItemData(handle, platform) {
  return await handle.evaluate((element, currentPlatform) => {
    const textOf = (selector) => {
      const node = element.querySelector(selector);
      return node ? (node.innerText || node.textContent || "").trim() : "";
    };
    const fullText = (element.innerText || element.textContent || "").trim().replace(/\s+/g, " ");
    const authorSelectors =
      currentPlatform === "youtube"
        ? ["#author-text", "a#author-text", ".author-text", "h3 a"]
        : [".user-name", ".reply-author", ".sub-user-name", ".name", ".bili-comment-user-name"];
    let author = "";
    for (const selector of authorSelectors) {
      author = textOf(selector);
      if (author) break;
    }
    const likeSelectors =
      currentPlatform === "youtube"
        ? ["#vote-count-middle", "#vote-count-left"]
        : [".like span", ".reply-like", ".like", ".bili-comment-action-like"];
    let likeText = "";
    for (const selector of likeSelectors) {
      likeText = textOf(selector);
      if (likeText) break;
    }
    const replySelectors =
      currentPlatform === "youtube"
        ? ["#more-replies", "ytd-button-renderer#more-replies"]
        : [".reply span", ".reply-btn", ".sub-reply-entry", ".bili-comment-action-reply"];
    let replyText = "";
    for (const selector of replySelectors) {
      replyText = textOf(selector);
      if (replyText) break;
    }
    const rect = element.getBoundingClientRect();
    return {
      author,
      visible_text: fullText,
      like_text: likeText,
      reply_text: replyText,
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
    };
  }, platform);
}

async function captureVisualItems(page, platform, outputDir, count) {
  if (platform === "bilibili") {
    const shadowItems = await captureBilibiliShadowVisualItems(page, outputDir, count);
    if (shadowItems.length > 0) return shadowItems;
  }
  const visualDir = path.join(outputDir, "comment_items");
  fs.mkdirSync(visualDir, { recursive: true });
  const visualItems = [];
  const seenText = new Set();
  let scrollAttempts = 0;
  while (visualItems.length < count && scrollAttempts < count * 4) {
    const arrayHandle = await visibleCommentItemHandles(page, platform);
    const properties = await arrayHandle.getProperties();
    const handles = Array.from(properties.values());
    for (const handle of handles) {
      if (visualItems.length >= count) break;
      try {
        const data = await extractCommentItemData(handle, platform);
        const key = data.visible_text.slice(0, 160);
        if (!data.visible_text || seenText.has(key)) continue;
        seenText.add(key);
        await handle.scrollIntoViewIfNeeded();
        await page.waitForTimeout(250);
        const box = await handle.boundingBox();
        if (!box || box.width < 240 || box.height < 56) continue;
        const filename = `${String(visualItems.length + 1).padStart(3, "0")}.png`;
        await handle.screenshot({ path: path.join(visualDir, filename) });
        visualItems.push({
          id: `${platform}_dom_${String(visualItems.length + 1).padStart(3, "0")}`,
          kind: "comment_dom_item",
          platform,
          path: `comment_items/${filename}`,
          author: data.author,
          visible_text: data.visible_text,
          like_text: data.like_text,
          reply_text: data.reply_text,
          rect: data.rect,
        });
      } catch (_error) {
        // Detached or hidden comment nodes are expected on virtualized pages.
      } finally {
        await handle.dispose().catch(() => {});
      }
    }
    await arrayHandle.dispose().catch(() => {});
    if (visualItems.length >= count) break;
    await page.mouse.wheel(0, Math.floor((await page.viewportSize()).height * 0.82));
    await page.waitForTimeout(platform === "bilibili" ? 900 : 1300);
    scrollAttempts += 1;
  }
  return visualItems;
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.url || !args.outputDir) {
    throw new Error("--url and --output-dir are required");
  }

  const platform = args.platform && args.platform !== "auto" ? args.platform : detectPlatform(args.url);
  const count = Math.max(1, Number(args.count || 4));
  const viewport = {
    width: Number(args.viewportWidth || 1280),
    height: Number(args.viewportHeight || 720),
  };
  const outputDir = path.resolve(args.outputDir);
  const screenshotDir = path.join(outputDir, "comment_screenshots");
  fs.mkdirSync(screenshotDir, { recursive: true });

  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox"],
  });
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    locale: "zh-CN",
  });
  const cookies = parseCookiesFile(args.cookies, args.url);
  if (cookies.length > 0) {
    await context.addCookies(cookies);
  }
  const page = await context.newPage();
  page.setDefaultTimeout(15000);

  const screenshots = [];
  let visualItems = [];
  let selector = "";
  let status = "ok";
  let error = "";
  let warning = "";
  let repeatedScrollCount = 0;
  let previousScrollY = -1;
  try {
    await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: Number(args.timeoutMs || 45000) });
    await page.waitForTimeout(2500);
    await closeKnownOverlays(page);
    selector = await scrollToComments(page, platform);
    if (!selector) status = "fallback";
    await page.waitForTimeout(platform === "bilibili" ? 3000 : 1200);
    visualItems = await captureVisualItems(page, platform, outputDir, count);

    for (let i = 0; i < count; i += 1) {
      const loginGateVisible = await detectLoginGate(page, platform);
      const filename = `${String(i + 1).padStart(3, "0")}.png`;
      const absPath = path.join(screenshotDir, filename);
      const scrollY = await page.evaluate(() => Math.round(window.scrollY));
      await page.screenshot({ path: absPath, fullPage: false });
      screenshots.push({
        index: i + 1,
        kind: "viewport",
        path: `comment_screenshots/${filename}`,
        scroll_y: scrollY,
        viewport,
        login_gate_visible: loginGateVisible,
      });
      if (loginGateVisible) {
        status = "login_required";
        warning = "The platform page shows a login gate for additional comments. Provide cookies to capture deeper comment screenshots.";
        break;
      }
      const beforeTextLength = await page.evaluate(() => (document.body ? document.body.innerText.length : 0));
      await page.mouse.move(Math.floor(viewport.width * 0.39), Math.max(120, viewport.height - 100));
      await page.evaluate((step) => {
        const scrolling = document.scrollingElement || document.documentElement;
        const maxScroll = Math.max(0, scrolling.scrollHeight - window.innerHeight);
        const target = Math.min(maxScroll, Math.round((scrolling.scrollTop || window.scrollY) + step));
        scrolling.scrollTop = target;
        window.scrollTo(0, target);
      }, Math.floor(viewport.height * 0.86));
      await page.waitForTimeout(450);
      for (let wheel = 0; wheel < 3; wheel += 1) {
        await page.mouse.wheel(0, Math.floor(viewport.height * 0.78));
        await page.waitForTimeout(420);
      }
      await page.evaluate(() => {
        const scrolling = document.scrollingElement || document.documentElement;
        const maxScroll = Math.max(0, scrolling.scrollHeight - window.innerHeight);
        const target = Math.min(maxScroll, Math.round((scrolling.scrollTop || window.scrollY) + window.innerHeight * 0.82));
        scrolling.scrollTop = target;
        window.scrollTo(0, target);
      });
      await page.waitForTimeout(1500);
      const nextScrollY = await page.evaluate(() => Math.round(window.scrollY));
      const afterTextLength = await page.evaluate(() => (document.body ? document.body.innerText.length : 0));
      const contentChanged = afterTextLength !== beforeTextLength;
      if ((nextScrollY === previousScrollY || nextScrollY === scrollY) && !contentChanged) {
        repeatedScrollCount += 1;
      } else {
        repeatedScrollCount = 0;
      }
      previousScrollY = nextScrollY;
      if (repeatedScrollCount >= 2 && i + 1 < count) {
        status = platform === "bilibili" ? "login_or_scroll_limit" : "scroll_limit";
        warning =
          platform === "bilibili"
            ? "The Bilibili comment page stopped scrolling before the requested screenshot count was reached. In anonymous mode this usually means a login gate; provide Bilibili cookies to capture deeper comments."
            : "The page stopped scrolling before the requested screenshot count was reached.";
        break;
      }
    }
  } catch (caught) {
    status = "failed";
    error = caught && caught.stack ? caught.stack : String(caught);
  } finally {
    await browser.close();
  }

  const manifest = {
    schema_version: "logiccut.comment_screenshots.v1",
    status,
    error,
    warning,
    platform,
    url: args.url,
    selector,
    viewport,
    screenshot_count: screenshots.length,
    screenshots,
    visual_item_count: visualItems.length,
    visual_items: visualItems,
    generated_at: new Date().toISOString(),
  };
  fs.writeFileSync(path.join(outputDir, "comment_screenshots.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(manifest)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error && error.stack ? error.stack : String(error)}\n`);
  process.exit(1);
});
