# Browser extraction reference

Read this when extraction returns `saved: false`, `Failed to fetch`, empty blocks, or the wrong page region.

## Normal path

1. `tools.browse.navigate({url, allowedOrigins:["<host>"], group:"web-to-audio", waitUntil:"settle", timeout:60000})` → keep the returned `tab`.
2. Wait for lazy content (scroll or `tools.browse.wait_for`) until text and images are present.
3. `tools.browse.eval({expression: /* full content of scripts/extract.js */, arg: {port:8765, name:"<key>", lang:"en"}, tab})` → returns `{blocks, images, chars, autoDetected, saved, status}`. Use `lang:"ru"` for Russian pages so image captions get the right prefix.
4. Validate: `saved === true`, text blocks > 0, first text block is the article. Inspect `page-<key>-blocks.json` with Python (block counts and first/last text) before continuing.

`browse.eval` invokes the expression as `(element, arg)` when `arg` is supplied. `extract.js` accepts both that and the no-argument form; custom expressions must do the same.

## Auto-detection and cleanup

- Candidate roots, in order: `article`, `main`, `[role="main"]`, `[itemprop="articleBody"]`, `.post-content`, `.article-content`, `.entry-content`, `.markdown-body`, `.prose`, `#content`, `.content`, `div.FgTq3`, `body`. Scored by text length, paragraph/heading counts, and link density; `body` is penalized.
- Title source: `titleSelector` → active LMS sidebar link → `og:title`/`twitter:title` → first `h1` → `document.title`.
- On a clone, removes scripts, nav, headers, footers, forms, buttons, hidden/aria-hidden nodes, cookie banners, ads, social/share, sidebars, related, comments, modals, popups, newsletters, breadcrumbs, and pagination.
- Collects headings, paragraphs, list items (with ordered/unordered metadata), quotes, code, tables, figcaptions, and `<img>` sources; deduplicates text and image URLs.
- If the result is a nav menu, cookie wall, or a wrapper of several articles, re-run with an explicit `contentSelector` (or `exclude`) found by inspecting the DOM, e.g.:

```js
const r = await tools.browse.eval({
  expression: `() => [...document.querySelectorAll('article, main, [role="main"]')].map(e => ({sel: e.tagName, len: e.innerText.length, sample: e.innerText.slice(0,120)}))`,
  tab
});
```

## CSP-blocked loopback POST (X/Twitter and similar)

Symptom: extraction returns `blocks`, `chars`, but `saved: false` with `TypeError: Failed to fetch`; the receiver log is empty. The site's Content Security Policy forbids `fetch()` to `http://127.0.0.1`.

Working fallback:

1. In the **content tab**, evaluate a variant of the extractor that builds the same `payload` object but returns it as a string in slices instead of POSTing:
   ```js
   const s = JSON.stringify(payload);
   const start = cfg.start || 0, len = cfg.len || 12000;
   return {total: s.length, start, slice: s.slice(start, start + len)};
   ```
   Call it repeatedly with `start = 0, 12000, 24000, …` until `start >= total`, then join the slices in the agent runtime into one JSON string.
2. Create a neutral tab with no site CSP:
   ```js
   const t = await tools.browse.tabs({
     action: "new", id: "poster", url: "about:blank",
     allowedOrigins: ["http://127.0.0.1:8765"]
   });
   ```
3. POST from that tab, passing the JSON string as `arg`:
   ```js
   const up = await tools.browse.eval({
     expression: `async (el, data) => { try { const r = await fetch('http://127.0.0.1:8765/save?name=page-<key>-blocks', {method:'POST', headers:{'Content-Type':'application/json'}, body:data}); return {ok:r.ok, status:r.status, bytes:data.length}; } catch(e) { return {error:String(e), bytes:data.length}; } }`,
     arg: payloadString, tab: t.tab
   });
   ```
4. Verify the saved file with Python (`json.loads`, block counts, first/last text) before running OCR. An `about:blank` tab has no site CSP, so the POST succeeds.
5. Close both the content and poster tabs during cleanup.

## X/Twitter article specifics

- The article body lives at `[data-testid="twitterArticleRichTextView"]`; the surrounding `article`/`main` also contains the timeline and controls.
- Image URLs are `https://pbs.twimg.com/media/...&name=900x900`. Replace `name=900x900` with `name=orig` in `page-<key>-blocks.json` before OCR/PDF for full resolution.
- `og:title` may be a marketing title; use the `h1` inside the article for accuracy.
- A real run produced 156 blocks (98 paragraphs, 25 headings, 15 list items, 13 images, 5 quotes) and 45k characters from one post — use that as a rough sanity range for long X articles.
