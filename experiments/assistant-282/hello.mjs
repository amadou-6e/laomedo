// One explicitly authorized real greeting; never retries a submission.
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
  const selection = page.getByRole("button",{name:"Choose model and effort"});
  await page.waitForFunction(() => {
    const control = document.querySelector('button[aria-label="Choose model and effort"]');
    return control && !control.disabled && !control.textContent.includes("Choose model");
  }, undefined, {timeout:90000});
  const visibleSelection = await selection.innerText();
  let message;
  let conversation;
  if (process.argv[2]) {
    conversation = process.argv[2];
    message = {id:process.argv[3]};
    await page.goto(metadata.base + "/assistant?conversation=" + conversation);
  } else {
  await page.getByRole("textbox",{name:"Message this assistant"}).fill("Hello. Reply with a short greeting only; do not use tools.");
  const send = page.getByRole("button",{name:"Start chat",exact:true});
  if (!(await send.isEnabled())) throw new Error("Greeting is not sendable without opening the picker");
  const acknowledgement = page.waitForResponse(response => response.url().endsWith("/messages") && response.request().method() === "POST",{timeout:30000});
  await send.click();
  const response = await acknowledgement;
  if (response.status() !== 202) throw new Error("Greeting dispatch refused: " + response.status());
  message = await response.json();
  conversation = new URL(page.url()).searchParams.get("conversation");
  if (!conversation) throw new Error("Conversation was not created");
  console.log(JSON.stringify({stage:"accepted",status:response.status(),conversation,message:message.id,visibleSelection}));
  }
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const detail = await page.evaluate(async id => {
      const response = await fetch("/api/v1/laomedo/assistant/conversations/" + id,{credentials:"same-origin",headers:{}});
      if (!response.ok) throw new Error("Cannot observe greeting: " + response.status);
      return response.json();
    },conversation);
    const observed = detail.messages.find(item => item.id === message.id);
    if (observed && ["completed","failed","cancelled","interrupted"].includes(observed.state)) {
      console.log(JSON.stringify({stage:"terminal",state:observed.state,error:observed.error_code,hasResponse:Boolean(observed.response),conversation}));
      await page.getByRole("button",{name:"Send",exact:true}).waitFor({timeout:15000});
      await page.locator('section[aria-label="Message and response"]').waitFor({state:"visible",timeout:30000});
      await page.locator(".prose").first().waitFor({state:"visible",timeout:30000});
      await page.screenshot({path:root + "/.tools/assistant-282-screens/hello-response.png",fullPage:true,animations:"disabled"});
      if (observed.state !== "completed" || !observed.response) throw new Error("Real greeting did not complete");
      break;
    }
    await page.waitForTimeout(1200);
  }
  if (Date.now() >= deadline) throw new Error("Real greeting observation timed out; no retry submitted");
} finally { await browser.close(); }
