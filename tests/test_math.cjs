const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = process.argv[2] || path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'app/index.html'), 'utf8');
const context = {
  katex: require(path.join(root, 'app/vendor/katex/katex.min.js')),
  crypto: require('node:crypto').webcrypto,
  esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
};
vm.createContext(context);
vm.runInContext(html.slice(html.indexOf('  function renderTex('), html.indexOf('  function splitFm(')), context);
for (const src of [String.raw`$x$`, String.raw`\(\sqrt[3]{x^2} + \frac{1}{2}\)`, String.raw`\[\begin{aligned}P(A|B)&=\frac{P(A\cap B)}{P(B)}\\x&=2\end{aligned}\]`, '$$\n\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}\n\n$$', String.raw`| Math | Value |
| --- | --- |
| $P(A|B)$ | $x_1$ |`, String.raw`- $\sum_{i=1}^n x_i$`]) {
  const result = context.md(src);
  assert.match(result, /class="katex"/);
  assert.match(result, /<math /);
  assert.doesNotMatch(result, /katex-error|BRAINMATH/);
}
for (const src of ['`$x$`', '```tex\n$x$\n```', String.raw`Cost: \$5 and \$10`, 'Price $5 and $10']) {
  assert.doesNotMatch(context.md(src), /class="katex"/);
}
assert.match(context.md(String.raw`$\unknowncommand{x}$ and $y$`), /cc0000/);
assert.match(context.md(String.raw`$\unknowncommand{x}$ and $y$`), /class="katex"/);
assert.match(context.md('`**literal**`'), /<code>\*\*literal\*\*<\/code>/);
assert.doesNotMatch(context.md(String.raw`$\text{<script>alert(1)</script>}$`), /<script>/);
for (const [, script] of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(script);
const study = path.join(root, 'personal-notes/sessions/2026-10-01-stat252-week3.md');
if (fs.existsSync(study)) {
  const rendered = context.md(fs.readFileSync(study, 'utf8'));
  assert.doesNotMatch(rendered, /BRAINMATH|katex-error/);
  assert.ok((rendered.match(/class="katex"/g) || []).length >= 10);
}
console.log('Math rendering regression checks passed');

