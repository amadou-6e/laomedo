// Real send with acknowledgement latency; one prompt, no automatic replay.
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
const require = createRequire("C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json");
const { chromium } = require("playwright");
const root = "C:/CodeWorkspace/laomedo";
const metadata = JSON.parse(await readFile(root + "/.tools/assistant-282-live.json", "utf8"));
const browser = await chromium.launch({headless:true,channel:"chrome"});
try {
  const page = await browser.newPage({viewport:{width:1041,height:895},colorScheme:"dark"});
  await page.goto(metadata.base + "/assistant");
  await page.waitForFunction(() => {
    const control = document.querySelector('button[aria-label="Choose model and effort"]');
    return control && !control.disabled && !control.textContent.includes("Choose model");
  },undefined,{timeout:90000});
  await page.evaluate(() => {
    window.__sendMotion = {retryTextSeen:false};
    new MutationObserver(() => {
      if (/Retry same submission|Reuses its original message ID|submission pending/.test(document.body.textContent)) window.__sendMotion.retryTextSeen = true;
    }).observe(document.body,{subtree:true,childList:true,characterData:true});
  });
  await page.route("**/conversations/*/messages", async route => {
    await new Promise(resolve => setTimeout(resolve,1200));
    await route.continue();
  });
  const prompt = "Say Hello! only. Do not use tools.";
  await page.getByRole("textbox",{name:"Message this assistant"}).fill(prompt);
  const acknowledgement = page.waitForResponse(response => response.url().endsWith("/messages") && response.request().method() === "POST",{timeout:30000});
  await page.getByRole("button",{name:"Start chat",exact:true}).click();
  await page.getByRole("status",{name:"Thinking",exact:true}).waitFor();
  const bubble = page.locator('section[aria-label="Message and response"] p.whitespace-pre-wrap');
  const initialBounds = await bubble.boundingBox();
  const animation = await page.locator(".laomedo-thinking-letter").evaluateAll(letters => letters.map(letter => ({name:getComputedStyle(letter).animationName,delay:getComputedStyle(letter).animationDelay})));
  if (animation.length !== 8 || animation.some(letter => letter.name !== "laomedo-thinking-lift") || new Set(animation.map(letter => letter.delay)).size !== 8) throw new Error("Thinking wave is not configured");
  await page.screenshot({path:root + "/.tools/assistant-282-screens/thinking-send.png",fullPage:true});
  await page.emulateMedia({reducedMotion:"reduce"});
  const reduced = await page.locator(".laomedo-thinking-letter").evaluateAll(letters => letters.every(letter => getComputedStyle(letter).animationName === "none"));
  if (!reduced) throw new Error("Reduced-motion preference was ignored");
  await page.emulateMedia({reducedMotion:"no-preference"});
  const response = await acknowledgement;
  if (response.status() !== 202) throw new Error("Dispatch refused: " + response.status());
  const message = await response.json();
  const conversation = new URL(page.url()).searchParams.get("conversation");
  console.log(JSON.stringify({stage:"accepted",conversation,message:message.id,status:response.status(),acknowledgementDelayMs:1200}));
  const deadline = Date.now()+180000;
  let completed = false;
  while (Date.now()<deadline) {
    const detail = await page.evaluate(async id => (await fetch("/api/v1/laomedo/assistant/conversations/"+id,{credentials:"same-origin",headers:{}})).json(),conversation);
    const observed = detail.messages.find(item => item.id === message.id);
    if (observed && ["completed","failed","cancelled","interrupted"].includes(observed.state)) {
      if (observed.state !== "completed" || !observed.response) throw new Error("Native run did not complete: " + observed.state);
      completed = true;
      break;
    }
    await page.waitForTimeout(1000);
  }
  if (!completed) throw new Error("Observation timeout; no retry sent");
  await page.locator(".prose").first().waitFor({state:"visible",timeout:30000});
  const finalBounds = await bubble.boundingBox();
  const retryTextSeen = await page.evaluate(() => window.__sendMotion.retryTextSeen);
  if (retryTextSeen) throw new Error("Retry boilerplate flashed during normal send");
  if (!initialBounds || !finalBounds || Math.abs(initialBounds.width-finalBounds.width)>1 || Math.abs(initialBounds.height-finalBounds.height)>1) throw new Error("User bubble changed geometry during acknowledgement");
  await page.screenshot({path:root+"/.tools/assistant-282-screens/thinking-complete.png",fullPage:true,animations:"disabled"});
  console.log(JSON.stringify({completed:true,message:message.id,noRetryTextFlash:true,stableBubbleGeometry:true,animatedLetters:animation.length,reducedMotionRespected:reduced}));
} finally {await browser.close();}
