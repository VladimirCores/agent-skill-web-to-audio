// Generic web-page extractor for tools.browse.eval.
// Pass this whole file as `expression`, with arg = config object and the tab id:
//   arg: {port: 8765, name: "my-article", contentSelector: "article", exclude: [".ads"]}
// It auto-detects the main content when no selector is given, then POSTs the
// extracted blocks to the loopback receiver (scripts/recv.py).

// browse.eval calls a function with (element, arg) when `arg` is supplied,
// and with no arguments otherwise; accept both shapes.
async (el, cfg) => {
  cfg = cfg || el || {};
  const port = cfg.port || 8765;
  const figPrefix = cfg.figcaptionPrefix || (cfg.lang === 'ru' ? 'Иллюстрация. ' : 'Illustration. ');
  const clean = s => (s || '').replace(/\u200b/g, '').replace(/\u00a0/g, ' ')
                               .replace(/[\t\r\n]+/g, ' ').replace(/\s+/g, ' ').trim();
  const href = location.href;

  // ---------- title (before any DOM cloning) ----------
  const titleEl = cfg.titleSelector ? document.querySelector(cfg.titleSelector) : null;
  const lmsTitle = document.querySelector('aside a.Rcoyt');
  const og = document.querySelector('meta[property="og:title"], meta[name="twitter:title"]');
  const h1 = document.querySelector('article h1, main h1, h1');
  let title = clean(titleEl && (titleEl.innerText || titleEl.textContent)) ||
              clean(lmsTitle && (lmsTitle.innerText || lmsTitle.textContent)) ||
              clean(og && og.content) || clean(h1 && h1.innerText) ||
              clean(document.title);
  if (cfg.titlePrefix) title = clean(cfg.titlePrefix) + ' — ' + title;

  // ---------- pick the content root ----------
  const defaults = [
    'article', 'main', '[role="main"]', '[itemprop="articleBody"]',
    '.post-content', '.article-content', '.article__body', '.entry-content',
    '.markdown-body', '.prose', '#content', '.content', 'div.FgTq3', 'body'
  ];
  let root = null;
  if (cfg.contentSelector) {
    root = document.querySelector(cfg.contentSelector);
    if (!root) return {error: 'contentSelector matched nothing: ' + cfg.contentSelector, url: href};
  } else {
    let best = -1;
    for (const sel of defaults) {
      const el = document.querySelector(sel);
      if (!el) continue;
      const text = clean(el.innerText || el.textContent);
      if (text.length < 120) continue;
      const linkLen = [...el.querySelectorAll('a')].reduce((n, a) => n + clean(a.innerText).length, 0);
      const linkRatio = linkLen / Math.max(text.length, 1);
      const score = text.length * (1 - Math.min(linkRatio, 0.95)) +
                    100 * el.querySelectorAll('p').length +
                    60 * el.querySelectorAll('h1,h2,h3,h4').length -
                    (sel === 'body' ? 1200 : 0);
      if (score > best) { best = score; root = el; }
    }
    if (!root) return {error: 'could not auto-detect content; pass contentSelector', url: href,
                       hint: 'Inspect the page and supply a CSS selector in your notes.'};
  }

  // ---------- strip navigation / chrome on a clone ----------
  const doc = root.cloneNode(true);
  const builtIn = [
    'script', 'style', 'noscript', 'svg', 'form', 'button', 'nav', 'header', 'footer',
    '[role="navigation"]', '[aria-hidden="true"]', '[hidden]',
    '.cookie', '.cookie-banner', '.ad', '.ads', '.advert', '.advertisement',
    '.social', '.share', '.sidebar', '.related', '.comments', '.comment-list',
    '.modal', '.popup', '.newsletter', '.subscribe', '.breadcrumbs', '.pagination'
  ];
  const excludes = builtIn.concat(cfg.exclude || []);
  for (const sel of excludes) {
    try { doc.querySelectorAll(sel).forEach(n => n.remove()); } catch (e) { /* bad selector */ }
  }

  // ---------- inline HTML sanitizer ----------
  const allowed = new Set(['B','STRONG','I','EM','U','S','SPAN','BR','A','CODE',
                           'BLOCKQUOTE','UL','OL','LI','TABLE','THEAD','TBODY','TR','TH','TD','PRE']);
  const safeHtml = el => {
    const c = el.cloneNode(true);
    c.querySelectorAll('*').forEach(n => {
      if (!allowed.has(n.tagName)) { n.replaceWith(...n.childNodes); return; }
      [...n.attributes].forEach(a => {
        const k = a.name.toLowerCase();
        if (k === 'href' && !/^https?:\/\//i.test(a.value)) n.removeAttribute(a.name);
        else if (k !== 'href') n.removeAttribute(a.name);
      });
    });
    return c.innerHTML;
  };

  // ---------- blocks ----------
  const blocks = [];
  const seenText = new Set();
  const seenSrc = new Set();
  const maxChars = cfg.maxChars || 250000;
  let total = 0;
  const push = b => {
    if (!b) return;
    if (b.text && seenText.has(b.text)) return;
    if (b.text) seenText.add(b.text);
    blocks.push(b);
    total += (b.text || '').length;
  };

  // images first (so their alt text is not repeated as a paragraph)
  if (cfg.includeImages !== false) {
    for (const img of doc.querySelectorAll('img')) {
      let src = img.currentSrc || img.src || img.getAttribute('data-src') || '';
      const ss = img.getAttribute('srcset');
      if (!src && ss) src = ss.split(',')[0].trim().split(' ')[0];
      if (!src || /^data:/i.test(src)) continue;
      if (/boomstream|poster|placeholder|1x1|pixel|tracking/i.test(src)) continue;
      if (seenSrc.has(src)) continue;
      seenSrc.add(src);
      push({type: 'img', src, w: img.naturalWidth || 0, h: img.naturalHeight || 0,
            alt: clean(img.alt)});
    }
  }

  const collected = [];
  const nodes = doc.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,table,figcaption,[data-block]');
  for (const el of nodes) {
    if (collected.some(a => a !== el && a.contains(el))) continue;
    collected.push(el);
    const tag = el.tagName.toUpperCase();
    let text = clean(el.innerText || el.textContent);
    if (!text || text.length < 2) continue;

    if (/^H[1-6]$/.test(tag)) {
      push({type: 'h', level: Number(tag[1]) || 2, text});
    } else if (tag === 'LI') {
      const parent = el.parentElement;
      push({type: 'li', text, ordered: !!(parent && parent.tagName === 'OL')});
    } else if (tag === 'BLOCKQUOTE') {
      push({type: 'quote', text});
    } else if (tag === 'PRE') {
      push({type: 'code', text: (el.textContent || '').trim()});
    } else if (tag === 'TABLE') {
      const rows = [...el.querySelectorAll('tr')].map(tr =>
        [...tr.querySelectorAll('th,td')].map(c => clean(c.innerText)).join(' | ')).filter(Boolean);
      if (rows.length) push({type: 'table', text: rows.join('. '), html: safeHtml(el)});
    } else if (tag === 'FIGCAPTION') {
      push({type: 'p', text: figPrefix + text, html: safeHtml(el)});
    } else {
      push({type: 'p', text, html: safeHtml(el)});
    }
    if (total >= maxChars) break;
  }

  // fallback: root has text but no structured blocks
  if (!blocks.some(b => b.type !== 'img')) {
    const text = clean(doc.innerText || doc.textContent);
    if (text) push({type: 'p', text: text.slice(0, maxChars)});
  }

  const key = cfg.name || (location.hostname + location.pathname)
    .replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'page';
  const desc = document.querySelector('meta[name="description"], meta[property="og:description"]');
  const site = document.querySelector('meta[property="og:site_name"]');
  const lang = document.documentElement.lang || '';
  const payload = {key, url: href, title, host: location.hostname,
                   meta: {description: clean(desc && desc.content),
                          site: clean(site && site.content), lang},
                   blocks};

  try {
    const res = await fetch(`http://127.0.0.1:${port}/save?name=page-${key}-blocks`, {
      method: 'POST', mode: 'cors', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    return {key, title, blocks: blocks.length,
            images: blocks.filter(b => b.type === 'img').length,
            chars: total, autoDetected: !cfg.contentSelector, saved: res.ok, status: res.status};
  } catch (e) {
    return {key, title, blocks: blocks.length, chars: total, saved: false,
            error: String(e), payload};
  }
}
