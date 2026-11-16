// Independent headless acceptance context, never attaches to the user's browser.
import { createRequire } from "node:module";
import { readFile, mkdir } from "node:fs/promises";
const require = createRequire("C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json");
const { chromium } = require("playwright");
const root = "C:/CodeWorkspace/laomedo";
const metadata = JSON.parse(await readFile(root + "/.tools/assistant-282-live.json", "utf8"));
const browser = await chromium.launch({headless:true,channel:"chrome"});
try {
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const page = await context.newPage();
  const failures = [];
  page.on("pageerror", error => failures.push(error.name + ":" + error.message.slice(0,180)));
  await page.goto(metadata.base + "/assistant?conversation=" + metadata.conversation);
  await page.getByRole("main", {name:"Application assistant"}).waitFor({timeout:90000});
  await page.getByRole("article", {name:"Saved draft: Assistant restart proof draft"}).waitFor({timeout:30000});
  await mkdir(root + "/.tools/assistant-282-screens", {recursive:true});
  await page.screenshot({path:root + "/.tools/assistant-282-screens/chat.png",fullPage:true});
  const link = page.getByRole("link",{name:/Open draft in new tab/}).first();
  const href = await link.getAttribute("href");
  const popupPromise = page.waitForEvent("popup");
  await link.click();
  const editor = await popupPromise;
  await editor.waitForURL("**" + href);
  await editor.locator(".react-flow__node").first().waitFor({timeout:45000});
  const nodes = await editor.locator(".react-flow__node").count();
  await editor.screenshot({path:root + "/.tools/assistant-282-screens/editor.png",fullPage:true});
  console.log(JSON.stringify({chatVisible:true,draftCardVisible:true,editorOpenedInSeparateTab:page.url().includes("/assistant"),nodes,failures}));
} finally { await browser.close(); }
