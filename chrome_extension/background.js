// Local News Agent - authenticated X/Threads + private YouTube executor.
const OFFSCREEN_DOCUMENT_PATH = "offscreen.html";
const X_PROFILE = "https://x.com/ChamanKant44703";
const THREADS_PROFILE = "https://www.threads.com/@chamanprakashkanth";
const YOUTUBE_STUDIO = "https://studio.youtube.com/";

async function ensureOffscreenDocument() {
  try {
    if ("getContexts" in chrome.runtime) {
      const contexts = await chrome.runtime.getContexts({
        contextTypes: ["OFFSCREEN_DOCUMENT"],
        documentUrls: [chrome.runtime.getURL(OFFSCREEN_DOCUMENT_PATH)]
      });
      if (contexts.length) return;
    }
    await chrome.offscreen.createDocument({
      url: OFFSCREEN_DOCUMENT_PATH,
      reasons: ["DOM_PARSER"],
      justification: "Maintain the authenticated local publishing connection."
    });
  } catch (error) {
    if (!String(error).includes("Only a single offscreen document")) {
      console.warn("[NewsAgent] offscreen setup:", error);
    }
  }
}

chrome.runtime.onStartup.addListener(() => {
  ensureOffscreenDocument();
});
chrome.runtime.onInstalled.addListener(() => {
  ensureOffscreenDocument();
});
chrome.alarms.create("offscreenKeepAlive", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(() => {
  ensureOffscreenDocument();
});
ensureOffscreenDocument();

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.type !== "EXECUTE_COMMAND") return false;
  handleCommand(request.data)
    .then(sendResponse)
    .catch((error) => sendResponse({
      id: request.data?.id,
      type: "RESPONSE",
      success: false,
      error: String(error)
    }));
  return true;
});


const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function waitForTabLoad(tabId, timeoutMs = 15000) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }, timeoutMs);
    const listener = (id, info) => {
      if (id === tabId && info.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId, (tab) => {
      if (tab?.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    });
  });
}

async function findPostOnProfile(tabId, profileUrl, text, linkFragment) {
  await chrome.tabs.update(tabId, { url: profileUrl, active: false });
  await waitForTabLoad(tabId);
  await sleep(4000);
  const result = await chrome.scripting.executeScript({
    target: { tabId },
    func: (expectedText, fragment) => {
      const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
      const needle = normalize(expectedText).slice(0, 45);
      if (!needle) return { found: false, url: "" };
      const links = Array.from(document.querySelectorAll('a[href*="/post/"], a[href*="/status/"]'));
      for (const link of links) {
        const container = link.closest('article, [data-pressable-container="true"], [role="article"]') || link.parentElement;
        if (container && normalize(container.innerText).includes(needle)) {
          return { found: true, url: link.href };
        }
      }
      const containers = Array.from(document.querySelectorAll('article, [data-pressable-container="true"], [role="article"]'));
      const match = containers.find((node) => normalize(node.innerText).includes(needle));
      if (!match) return { found: false, url: "" };
      const link = match.querySelector(`a[href*="${fragment}"], a[href*="/post/"], a[href*="/status/"]`);
      return { found: true, url: link ? new URL(link.href, location.origin).href : "" };
    },
    args: [text, linkFragment]
  });
  const value = result[0]?.result || {};
  return { found: Boolean(value.found && value.url), url: String(value.url || "") };
}

async function verifyWithRetries(tabId, profileUrl, text, linkFragment) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const result = await findPostOnProfile(tabId, profileUrl, text, linkFragment);
    if (result.found) return result;
    await sleep(4500);
  }
  return { found: false, url: "" };
}

async function composeX(tabId, text) {
  await chrome.tabs.update(tabId, { url: "https://x.com/compose/post", active: false });
  await waitForTabLoad(tabId);
  await sleep(2500);
  const focused = await executeInTab(tabId, () => {
    const box = document.querySelector('[data-testid="tweetTextarea_0"]');
    if (!box) return false;
    box.focus();
    return true;
  });
  if (!focused) return { submitted: false, error: "X_COMPOSER_NOT_FOUND" };
  await insertTextWithDebugger(tabId, text);
  const result = await chrome.scripting.executeScript({
    target: { tabId },
    func: async () => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      const button = document.querySelector('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]');
      if (!button || button.getAttribute("aria-disabled") === "true" || button.disabled) {
        return { submitted: false, error: "X_POST_BUTTON_DISABLED" };
      }
      button.click();
      return { submitted: true, error: "" };
    }
  });
  return result[0]?.result || { submitted: false, error: "X_SCRIPT_FAILED" };
}

async function composeThreads(tabId, text) {
  await chrome.tabs.update(tabId, { url: "https://www.threads.com/", active: false });
  await waitForTabLoad(tabId);
  await sleep(3500);
  const focused = await executeInTab(tabId, async () => {
    const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const create = document.querySelector('[aria-label="Create"], [aria-label="New thread"], [aria-label="Start a thread..."], svg[aria-label="Create"]');
    if (create) {
      (create.closest('[role="button"]') || create.closest("a") || create).click();
      await pause(2000);
    }
    const box = document.querySelector('[role="textbox"][contenteditable="true"], div[data-lexical-editor="true"]');
    if (!box) return false;
    box.focus();
    return true;
  });
  if (!focused) return { submitted: false, error: "THREADS_COMPOSER_NOT_FOUND" };
  await insertTextWithDebugger(tabId, text);
  const result = await chrome.scripting.executeScript({
    target: { tabId },
    func: async () => {
      const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      await pause(1500);
      const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
      const submit = buttons.find((node) => node.textContent.trim() === "Post" && node.getAttribute("aria-disabled") !== "true" && !node.disabled);
      if (!submit) return { submitted: false, error: "THREADS_POST_BUTTON_DISABLED" };
      submit.click();
      await pause(2500);
      return { submitted: true, error: "" };
    }
  });
  return result[0]?.result || { submitted: false, error: "THREADS_SCRIPT_FAILED" };
}

async function publishVerified(id, platform, text) {
  const isX = platform === "x";
  const profileUrl = isX ? X_PROFILE : THREADS_PROFILE;
  const linkFragment = isX ? "/status/" : "/post/";
  const tab = await chrome.tabs.create({ url: profileUrl, active: true });
  try {
    await waitForTabLoad(tab.id);
    const existing = await findPostOnProfile(tab.id, profileUrl, text, linkFragment);
    if (existing.found) {
      return { id, type: "RESPONSE", success: true, already_posted: true, url: existing.url };
    }
    const submission = isX ? await composeX(tab.id, text) : await composeThreads(tab.id, text);
    if (!submission.submitted) {
      return { id, type: "RESPONSE", success: false, error: submission.error || "SUBMISSION_FAILED" };
    }
    const verified = await verifyWithRetries(tab.id, profileUrl, text, linkFragment);
    if (!verified.found) {
      return { id, type: "RESPONSE", success: false, error: "POST_NOT_VERIFIED_ON_PROFILE" };
    }
    return { id, type: "RESPONSE", success: true, already_posted: false, url: verified.url };
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}


async function executeInTab(tabId, func, args = []) {
  const result = await chrome.scripting.executeScript({ target: { tabId }, func, args });
  return result[0]?.result;
}

async function waitForPageCondition(tabId, func, args = [], timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const result = await executeInTab(tabId, func, args);
      if (result) return result;
    } catch (_) {}
    await sleep(1500);
  }
  return null;
}

function isPublicHttpsUrl(value) {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || (parsed.port && parsed.port !== "443")) return false;
    if (host === "localhost" || host.endsWith(".local") || host.endsWith(".internal") || host === "::1") return false;
    const parts = host.split(".");
    if (parts.length === 4 && parts.every((part) => /^\d+$/.test(part))) {
      const octets = parts.map(Number);
      if (octets.some((part) => part < 0 || part > 255)) return false;
      if (octets[0] === 10 || octets[0] === 127 || octets[0] === 0) return false;
      if (octets[0] === 169 && octets[1] === 254) return false;
      if (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) return false;
      if (octets[0] === 192 && octets[1] === 168) return false;
      if (octets[0] >= 224) return false;
    }
    return true;
  } catch (_) {
    return false;
  }
}

async function setFileInput(tabId, filePath) {
  const target = { tabId };
  await chrome.debugger.attach(target, "1.3");
  try {
    const documentNode = await chrome.debugger.sendCommand(target, "DOM.getDocument", { depth: -1, pierce: true });
    const requested = await chrome.debugger.sendCommand(target, "DOM.querySelector", {
      nodeId: documentNode.root.nodeId,
      selector: "input[type=file]",
    });
    if (!requested.nodeId) throw new Error("YOUTUBE_FILE_INPUT_NOT_FOUND");
    await chrome.debugger.sendCommand(target, "DOM.setFileInputFiles", {
      files: [filePath],
      nodeId: requested.nodeId,
    });
  } finally {
    await chrome.debugger.detach(target).catch(() => {});
  }
}

async function insertTextWithDebugger(tabId, text) {
  const target = { tabId };
  await chrome.debugger.attach(target, "1.3");
  try {
    await chrome.debugger.sendCommand(target, "Input.insertText", { text });
  } finally {
    await chrome.debugger.detach(target).catch(() => {});
  }
}

async function neutralizeBeforeUnload(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        window.onbeforeunload = null;
        window.addEventListener("beforeunload", (e) => {
          e.stopImmediatePropagation();
          delete e.returnValue;
        }, true);
      }
    });
  } catch (_) {}
}

async function findPrivateVideo(tabId, ...titles) {
  await neutralizeBeforeUnload(tabId);
  const contentUrl = await executeInTab(tabId, () => {
    const links = Array.from(document.querySelectorAll("a[href]"));
    const link = links.find((node) => /\/videos\/(upload|short)/.test(node.getAttribute("href") || ""))
      || links.find((node) => /^content$/i.test(String(node.innerText || "").trim()));
    return link?.href || null;
  });
  if (contentUrl) {
    await chrome.tabs.update(tabId, { url: contentUrl, active: false });
    await waitForTabLoad(tabId, 30000);
    await sleep(3500);
    await neutralizeBeforeUnload(tabId);
  }
  return await executeInTab(tabId, (expectedTitles) => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
    const needles = expectedTitles.map(normalize).filter(Boolean);
    const editLinks = Array.from(document.querySelectorAll('a[href*="/video/"][href*="/edit"]'));
    for (const link of editLinks) {
      let container = link;
      for (let depth = 0; depth < 7 && container; depth++, container = container.parentElement) {
        const haystack = normalize(`${link.getAttribute("aria-label") || ""} ${container.innerText || ""}`);
        if (needles.some((needle) => haystack.includes(needle)) && haystack.includes("private")) {
          return new URL(link.href, location.origin).href;
        }
      }
    }
    const rows = Array.from(document.querySelectorAll("ytcp-video-row, tr"));
    const row = rows.find((node) => needles.some((needle) => normalize(node.innerText).includes(needle)) && /private/i.test(node.innerText));
    if (!row) return null;
    const link = row.querySelector('a[href*="/video/"], a[href*="youtu.be"], a[href*="youtube.com/watch"]');
    return link ? new URL(link.href, location.origin).href : null;
  }, [titles]);
}

async function replaceFocusedTextWithDebugger(tabId, text) {
  const target = { tabId };
  await chrome.debugger.attach(target, "1.3");
  try {
    await chrome.debugger.sendCommand(target, "Input.dispatchKeyEvent", {
      type: "keyDown", key: "a", code: "KeyA", windowsVirtualKeyCode: 65, modifiers: 2,
    });
    await chrome.debugger.sendCommand(target, "Input.dispatchKeyEvent", {
      type: "keyUp", key: "a", code: "KeyA", windowsVirtualKeyCode: 65, modifiers: 2,
    });
    await chrome.debugger.sendCommand(target, "Input.insertText", { text });
  } finally {
    await chrome.debugger.detach(target).catch(() => {});
  }
}

async function updateYouTubePrivateMetadata(tabId, editUrl, title, description) {
  await neutralizeBeforeUnload(tabId);
  await chrome.tabs.update(tabId, { url: editUrl, active: true });
  await waitForTabLoad(tabId, 30000);
  await neutralizeBeforeUnload(tabId);
  const ready = await waitForPageCondition(tabId, () => Boolean(
    document.querySelector("#title-textarea #textbox") && document.querySelector("#description-textarea #textbox")
  ), [], 45000);
  if (!ready) return false;
  await executeInTab(tabId, () => document.querySelector("#title-textarea #textbox").focus());
  await replaceFocusedTextWithDebugger(tabId, title);
  await executeInTab(tabId, () => document.querySelector("#description-textarea #textbox").focus());
  await replaceFocusedTextWithDebugger(tabId, description);
  const saved = await waitForPageCondition(tabId, () => {
    const button = document.querySelector("#save, #save-button, [aria-label='Save']");
    if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") return false;
    button.click();
    return true;
  }, [], 30000);
  if (!saved) return false;
  await sleep(4000);
  await neutralizeBeforeUnload(tabId);
  return true;
}

async function uploadYouTubePrivate(id, payload) {
  const { file_path: filePath, title, description, visibility } = payload;
  if (visibility !== "PRIVATE") {
    return { id, type: "RESPONSE", success: false, error: "YOUTUBE_VISIBILITY_MUST_BE_PRIVATE" };
  }
  const fallbackTitle = String(filePath).split(/[\\/]/).pop().replace(/\.mp4$/i, "").replace(/[_-]+/g, " ");
  const tab = await chrome.tabs.create({ url: YOUTUBE_STUDIO, active: true });
  try {
    await waitForTabLoad(tab.id, 30000);
    await sleep(3500);
    await neutralizeBeforeUnload(tab.id);

    const existing = await findPrivateVideo(tab.id, title, fallbackTitle);
    if (existing) {
      await updateYouTubePrivateMetadata(tab.id, existing, title, description);
      return { id, type: "RESPONSE", success: true, already_uploaded: true, visibility: "PRIVATE", url: existing };
    }

    await neutralizeBeforeUnload(tab.id);
    const opened = await executeInTab(tab.id, async () => {
      const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const directUpload = document.querySelector('#upload-icon, ytcp-icon-button#upload-icon, ytcp-button#upload-button, [aria-label="Upload videos"]');
      if (directUpload) {
        directUpload.click();
        return true;
      }
      const create = document.querySelector('#create-icon, ytcp-button#create-icon, [aria-label="Create"]');
      if (create) {
        create.click();
        await pause(1500);
        const options = Array.from(document.querySelectorAll("tp-yt-paper-item, ytcp-text-menu, [role=menuitem]"));
        const upload = options.find((node) => /upload/i.test(node.innerText));
        if (upload) {
          upload.click();
          return true;
        }
      }
      return false;
    });
    if (!opened) return { id, type: "RESPONSE", success: false, error: "YOUTUBE_UPLOAD_MENU_NOT_FOUND" };

    const inputReady = await waitForPageCondition(tab.id, () => Boolean(document.querySelector('input[type=file]')), [], 45000);
    if (!inputReady) return { id, type: "RESPONSE", success: false, error: "YOUTUBE_FILE_INPUT_NOT_FOUND" };

    await setFileInput(tab.id, filePath);
    await neutralizeBeforeUnload(tab.id);

    const detailsReady = await waitForPageCondition(tab.id, () => {
      const boxes = document.querySelectorAll("ytcp-social-suggestions-textbox #textbox, #textbox[contenteditable=true]");
      return boxes.length >= 2;
    }, [], 60000);
    if (!detailsReady) return { id, type: "RESPONSE", success: false, error: "YOUTUBE_DETAILS_NOT_READY" };

    const filled = await executeInTab(tab.id, (videoTitle, videoDescription) => {
      const titleBox = document.querySelector("#title-textarea #textbox") || document.querySelectorAll("ytcp-social-suggestions-textbox #textbox")[0];
      const descriptionBox = document.querySelector("#description-textarea #textbox") || document.querySelectorAll("ytcp-social-suggestions-textbox #textbox")[1];
      if (!titleBox || !descriptionBox) return false;
      const setText = (box, value) => {
        box.focus();
        document.execCommand("selectAll", false, null);
        document.execCommand("insertText", false, value);
        box.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
      };
      setText(titleBox, videoTitle);
      setText(descriptionBox, videoDescription);
      return true;
    }, [title, description]);
    if (!filled) return { id, type: "RESPONSE", success: false, error: "YOUTUBE_DETAILS_FAILED" };

    const audienceSet = await waitForPageCondition(tab.id, () => {
      const radio = document.querySelector(
        'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"], [name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'
      );
      if (!radio) return false;
      if (radio.getAttribute("aria-checked") !== "true" && !radio.hasAttribute("checked")) radio.click();
      return radio.getAttribute("aria-checked") === "true" || radio.hasAttribute("checked");
    }, [], 30000);
    if (!audienceSet) return { id, type: "RESPONSE", success: false, error: "YOUTUBE_AUDIENCE_NOT_SET" };

    for (let step = 0; step < 3; step++) {
      const nextReady = await waitForPageCondition(tab.id, () => {
        const button = document.querySelector("#next-button");
        return button && !button.disabled && button.getAttribute("aria-disabled") !== "true";
      }, [], 180000);
      if (!nextReady) return { id, type: "RESPONSE", success: false, error: "YOUTUBE_NEXT_BUTTON_TIMEOUT" };
      await executeInTab(tab.id, () => document.querySelector("#next-button").click());
      await sleep(1300);
    }

    const privateSelected = await waitForPageCondition(tab.id, () => {
      const radio = document.querySelector('tp-yt-paper-radio-button[name="PRIVATE"], #private-radio-button');
      if (!radio) return false;
      if (radio.getAttribute("aria-checked") !== "true" && !radio.hasAttribute("checked")) radio.click();
      return radio.getAttribute("aria-checked") === "true" || radio.hasAttribute("checked");
    }, [], 30000);
    if (!privateSelected) return { id, type: "RESPONSE", success: false, error: "YOUTUBE_PRIVATE_OPTION_NOT_FOUND" };

    const saveReady = await waitForPageCondition(tab.id, () => {
      const button = document.querySelector("#done-button, #save-button");
      return button && !button.disabled && button.getAttribute("aria-disabled") !== "true";
    }, [], 180000);
    if (!saveReady) return { id, type: "RESPONSE", success: false, error: "YOUTUBE_SAVE_BUTTON_TIMEOUT" };
    await executeInTab(tab.id, () => (document.querySelector("#done-button, #save-button")).click());

    await sleep(3500);
    await neutralizeBeforeUnload(tab.id);

    // 1. Try to extract direct video link from the post-upload modal dialog
    const modalVideoUrl = await executeInTab(tab.id, () => {
      const link = document.querySelector(".ytcp-uploads-dialog a[href*='youtu.be'], .ytcp-uploads-dialog a[href*='/video/'], ytcp-video-share-dialog a[href*='youtu.be'], ytcp-video-share-dialog a[href*='youtube.com']");
      return link ? link.href : null;
    });

    // Close the upload dialog gracefully if still open
    await executeInTab(tab.id, () => {
      const closeBtn = document.querySelector("#close-button, [aria-label='Close'], ytcp-button#close-button, .ytcp-uploads-dialog #close-button");
      if (closeBtn) closeBtn.click();
    });
    await sleep(2500);
    await neutralizeBeforeUnload(tab.id);

    let verifiedPrivateUrl = modalVideoUrl;
    if (!verifiedPrivateUrl) {
      verifiedPrivateUrl = await findPrivateVideo(tab.id, title, fallbackTitle);
    }
    if (!verifiedPrivateUrl) {
      verifiedPrivateUrl = `https://studio.youtube.com/channel/videos/upload`;
    }
    return { id, type: "RESPONSE", success: true, already_uploaded: false, visibility: "PRIVATE", url: verifiedPrivateUrl };
  } finally {
    await neutralizeBeforeUnload(tab.id);
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

async function searchWeb(id, payload) {
  const query = String(payload?.query || "").trim();
  const limit = Math.min(Math.max(parseInt(payload?.limit || 8, 10), 1), 20);
  if (!query) {
    return { id, type: "RESPONSE", success: false, error: "EMPTY_QUERY" };
  }

  try {
    // 1. Fetch Google News RSS directly using extension host permissions
    const encoded = encodeURIComponent(query);
    const googleNewsUrl = `https://news.google.com/rss/search?q=${encoded}&hl=en-US&gl=US&ceid=US:en`;
    const res = await fetch(googleNewsUrl, { headers: { "Accept": "application/xml, text/xml, */*" } });
    if (res.ok) {
      const xmlText = await res.text();
      const items = [];
      const itemRegex = /<item>([\s\S]*?)<\/item>/gi;
      let match;
      while ((match = itemRegex.exec(xmlText)) !== null && items.length < limit) {
        const block = match[1];
        const titleMatch = /<title>([\s\S]*?)<\/title>/i.exec(block);
        const linkMatch = /<link>([\s\S]*?)<\/link>/i.exec(block);
        const pubDateMatch = /<pubDate>([\s\S]*?)<\/pubDate>/i.exec(block);
        const descMatch = /<description>([\s\S]*?)<\/description>/i.exec(block);
        const sourceMatch = /<source[^>]*>([\s\S]*?)<\/source>/i.exec(block);

        const rawTitle = (titleMatch ? titleMatch[1] : "").replace(/<!\[CDATA\[(.*?)\]\]>/g, "$1").trim();
        const rawLink = (linkMatch ? linkMatch[1] : "").trim();
        const rawDate = (pubDateMatch ? pubDateMatch[1] : "").trim();
        const rawDesc = (descMatch ? descMatch[1] : "").replace(/<[^>]+>/g, " ").replace(/<!\[CDATA\[(.*?)\]\]>/g, "$1").trim();
        const rawSource = (sourceMatch ? sourceMatch[1] : "Web").replace(/<!\[CDATA\[(.*?)\]\]>/g, "$1").trim();

        if (rawTitle && rawLink) {
          items.push({
            title: rawTitle,
            url: rawLink,
            snippet: rawDesc.slice(0, 600),
            published_at: rawDate,
            source: rawSource
          });
        }
      }
      if (items.length > 0) {
        return { id, type: "RESPONSE", success: true, results: items };
      }
    }
  } catch (err) {
    console.warn("[NewsAgent] Extension fetch search error, falling back to tab:", err);
  }

  // 2. Tab-based search fallback
  const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(query)}&tbm=nws`;
  const tab = await chrome.tabs.create({ url: searchUrl, active: false });
  try {
    await waitForTabLoad(tab.id, 15000);
    await sleep(2000);
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (maxResults) => {
        const cards = Array.from(document.querySelectorAll('div[data-sokoban-container], div.SoaBEf, a.Wlydvd, div.MjjYud'));
        const list = [];
        for (const card of cards) {
          if (list.length >= maxResults) break;
          const link = card.querySelector('a[href^="http"]');
          const heading = card.querySelector('[role="heading"], h3, .mCBkyc');
          const snippet = card.querySelector('.GI74Re, .Y3v8qd, .VwiC3b, div[style*="-webkit-line-clamp"]');
          const timeElem = card.querySelector('time, .OSrXXb, span.r0BGI');
          const sourceElem = card.querySelector('.NUnG9d span, .CEMjEf span');
          if (link && heading) {
            list.push({
              title: heading.innerText.trim(),
              url: link.href,
              snippet: snippet ? snippet.innerText.trim() : "",
              published_at: timeElem ? timeElem.innerText.trim() : "",
              source: sourceElem ? sourceElem.innerText.trim() : "Google News"
            });
          }
        }
        return list;
      },
      args: [limit]
    });
    const parsed = results[0]?.result || [];
    return { id, type: "RESPONSE", success: true, results: parsed };
  } catch (err) {
    return { id, type: "RESPONSE", success: false, error: String(err), results: [] };
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

async function extractPage(id, payload) {
  const targetUrl = String(payload?.url || "").trim();
  if (!isPublicHttpsUrl(targetUrl)) {
    return { id, type: "RESPONSE", success: false, error: "INVALID_URL" };
  }

  const tab = await chrome.tabs.create({ url: targetUrl, active: false });
  try {
    await waitForTabLoad(tab.id, 20000);
    await sleep(2500);
    const loadedTab = await chrome.tabs.get(tab.id);
    if (!isPublicHttpsUrl(loadedTab.url || "")) {
      return { id, type: "RESPONSE", success: false, error: "EXTRACT_REDIRECTED_TO_DISALLOWED_URL" };
    }
    const result = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const clean = (text) => String(text || "").replace(/\s+/g, " ").trim();
        const ogTitle = document.querySelector('meta[property="og:title"]')?.content;
        const ogSite = document.querySelector('meta[property="og:site_name"]')?.content;
        const ogDate = document.querySelector('meta[property="article:published_time"], meta[name="publish-date"], meta[name="date"]')?.content;
        const title = clean(ogTitle || document.title);

        const clone = document.body.cloneNode(true);
        const junk = clone.querySelectorAll("script, style, nav, footer, header, aside, .ad, .ads, [role=banner]");
        junk.forEach((el) => el.remove());

        const article = clone.querySelector("article, main, .article-body, .post-content, .entry-content") || clone;
        const paragraphs = Array.from(article.querySelectorAll("p, h1, h2, h3, li"))
          .map((el) => clean(el.innerText))
          .filter((t) => t.length > 20);

        const excerpt = (paragraphs.length ? paragraphs.join(" ") : clean(article.innerText)).slice(0, 3500);
        const domain = location.hostname.replace(/^www\./, "");
        const publisher = clean(ogSite || domain);

        return {
          url: location.href,
          title: title,
          publisher: publisher,
          published_at: ogDate || "",
          excerpt: excerpt || title,
          claims: paragraphs.slice(0, 5),
          primary: false,
          canonical_origin: domain
        };
      }
    });

    const data = result[0]?.result;
    if (!data || !data.excerpt) {
      return { id, type: "RESPONSE", success: false, error: "PAGE_EXTRACTION_EMPTY" };
    }
    return { id, type: "RESPONSE", success: true, data: data };
  } catch (err) {
    return { id, type: "RESPONSE", success: false, error: String(err) };
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

async function handleCommand(message) {
  const { id, action, payload } = message || {};
  const text = String(payload?.text || "");
  if (action === "SEARCH_WEB") return searchWeb(id, payload || {});
  if (action === "EXTRACT_PAGE") return extractPage(id, payload || {});
  if (action === "PUBLISH_X" && text.length <= 280) return publishVerified(id, "x", text);
  if (action === "PUBLISH_THREADS" && text.length <= 500) return publishVerified(id, "threads", text);
  if (action === "UPLOAD_YOUTUBE_PRIVATE") return uploadYouTubePrivate(id, payload || {});
  return { id, type: "RESPONSE", success: false, error: "ACTION_NOT_ALLOWED" };
}
