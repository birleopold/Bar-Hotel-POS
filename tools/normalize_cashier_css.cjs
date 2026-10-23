// One-time cleanup of the inherited cashier cascade. Requires Playwright.
// Parse with Chromium rather than rewriting CSS using regular expressions.
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  const page = await browser.newPage();
  const path = 'backend/apps/staff/static/staff/retail-cashier.css';
  const source = fs.readFileSync(path, 'utf8');
  const css = await page.evaluate(source => {
    const sheet = new CSSStyleSheet(); sheet.replaceSync(source);
    const seen = new Map();
    function clean(rules, context) {
      const result = [];
      for (const rule of Array.from(rules).reverse()) {
        if (rule.cssRules) {
          const nested = clean(rule.cssRules, context + '|' + rule.conditionText);
          if (nested) result.unshift(rule.cssText.split('{')[0] + '{\n' + nested + '\n}');
        } else if (rule.style && rule.selectorText) {
          const key = context + '|' + rule.selectorText;
          const later = seen.get(key) || new Map();
          for (const name of Array.from(rule.style)) {
            // Catalogue geometry has one responsive owner below. Remove the
            // inherited competing breakpoints, including the 155px cap.
            if (rule.selectorText.includes('.staff-pos-menu-grid') &&
                ['grid-template-columns', 'gap', 'justify-content'].includes(name)) {
              rule.style.removeProperty(name); continue;
            }
            const important = rule.style.getPropertyPriority(name) === 'important';
            if (later.has(name) && (later.get(name) || !important)) rule.style.removeProperty(name);
            else later.set(name, important);
          }
          seen.set(key, later);
          if (rule.style.length) result.unshift(rule.cssText);
        } else result.unshift(rule.cssText);
      }
      return result.join('\n');
    }
    return clean(sheet.cssRules, '');
  }, source);
  fs.writeFileSync(path, '/* Retail cashier: consolidated cascade. Shared foundation: fizo-fresh.css.\n * Business workflow styles: retail-workflows.css. No additional override file. */\n' + css + '\n');
  await browser.close();
})();
