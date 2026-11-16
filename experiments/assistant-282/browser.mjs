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
  await mkdir(root + "/.tools/assistant-282-screens", {recursive:true});
  await page.goto(metadata.base + "/assistant");
  await page.getByPlaceholder("Start chat…").waitFor({timeout:90000});
  await page.getByRole("option", {name:"gpt-6-luna",exact:true}).waitFor({state:"attached",timeout:30000});
  await page.getByLabel("Assistant model",{exact:true}).selectOption("gpt-6-luna");
  await page.getByLabel("Assistant reasoning effort",{exact:true}).selectOption("medium");
  await page.screenshot({path:root + "/.tools/assistant-282-screens/feedback-empty.png",fullPage:true});
  await page.getByRole("button",{name:"Collapse conversations",exact:true}).click();
  await page.getByRole("button",{name:"Expand conversations",exact:true}).waitFor();
  if (await page.getByRole("complementary",{name:"Conversations"}).isVisible()) throw new Error("History did not collapse");
  await page.screenshot({path:root + "/.tools/assistant-282-screens/feedback-collapsed.png",fullPage:true});
  await page.getByRole("button",{name:"Expand conversations",exact:true}).click();
  await page.goto(metadata.base + "/assistant?conversation=" + metadata.conversation);
  await page.getByRole("main", {name:"Application assistant"}).waitFor({timeout:90000});
  await page.getByRole("article", {name:"Saved draft: Assistant restart proof draft"}).waitFor({timeout:30000});
  await mkdir(root + "/.tools/assistant-282-screens", {recursive:true});
  await page.screenshot({path:root + "/.tools/assistant-282-screens/chat.png",fullPage:true});
  await page.getByLabel("Assistant messages and saved drafts",{exact:true}).evaluate(element => { element.scrollTop = 0; });
  await page.getByLabel("Tool calls",{exact:true}).first().waitFor();
  await page.getByText("search_components",{exact:true}).first().waitFor();
  await page.screenshot({path:root + "/.tools/assistant-282-screens/feedback-tools.png",fullPage:true});
  const link = page.getByRole("link",{name:/Open draft in new tab/}).first();
  const href = await link.getAttribute("href");
  const popupPromise = page.waitForEvent("popup");
  await link.click();
  const editor = await popupPromise;
  await editor.waitForURL("**" + href);
  await editor.locator(".react-flow__node").first().waitFor({timeout:45000});
  const nodes = await editor.locator(".react-flow__node").count();
  const edges = await editor.locator(".react-flow__edge").count();
  const attachedEdges = await editor.evaluate(() => {
    const nodeIds = [...document.querySelectorAll(".react-flow__node")].map(node => node.getAttribute("data-id"));
    return [...document.querySelectorAll(".react-flow__edge")].every(edge => {
      const identity = edge.getAttribute("data-id") || "";
      const path = edge.querySelector("path.react-flow__edge-path");
      return nodeIds.every(id => id && identity.includes(id)) && Boolean(path?.getAttribute("d"));
    });
  });
  if (nodes !== 2 || edges !== 1 || !attachedEdges) throw new Error("Expected one rendered edge joining the two draft nodes");
  await editor.screenshot({path:root + "/.tools/assistant-282-screens/editor.png",fullPage:true});
  console.log(JSON.stringify({chatVisible:true,draftCardVisible:true,editorOpenedInSeparateTab:page.url().includes("/assistant"),nodes,edges,attachedEdges,failures}));
} finally { await browser.close(); }
