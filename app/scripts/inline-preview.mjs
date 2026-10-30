// Packs the preview build into one HTML file (scripts and styles inline), so it
// can be published as a single page. Output: dist-preview/formatly-preview.html
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const dir = "dist-preview";
let html = readFileSync(join(dir, "index.html"), "utf8");

html = html.replace(/<link rel="stylesheet"[^>]*href="\/?([^"]+)"[^>]*>/g, (_, href) =>
  `<style>${readFileSync(join(dir, href), "utf8")}</style>`);
html = html.replace(/<script type="module"[^>]*src="\/?([^"]+)"[^>]*><\/script>/g, (_, src) =>
  `<script type="module">${readFileSync(join(dir, src), "utf8").replace(/<\/script/gi, "<\\/script")}</script>`);
html = html.replace(/<link rel="icon"[^>]*>/, "");

// The publishing page supplies the outer document; keep only what goes inside it.
const head = /<head>([\s\S]*?)<\/head>/.exec(html)[1]
  .replace(/<meta charset[^>]*>/, "").replace(/<meta name="viewport"[^>]*>/, "");
const body = /<body>([\s\S]*?)<\/body>/.exec(html)[1];
writeFileSync(join(dir, "formatly-preview.html"), `${head.trim()}\n${body.trim()}\n`);
console.log(`${dir}/formatly-preview.html: ${Math.round((head.length + body.length) / 1024)} KB`);
