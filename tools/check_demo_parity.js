// Extract the pure algorithm block from docs/index.html and run scenarios, so
// the browser demo can be compared against the Python pipeline.
//
// What parity means here: the *enumeration* must be identical (same dishes,
// same quantities, same order). Amounts deliberately differ — the demo prices
// from menu list prices, while the CLI uses calculate-price, which includes
// coupons. Treating list price as the payable total is exactly what this
// project refuses to do, so the amounts are not the thing to compare.
const fs = require('fs');
const html = fs.readFileSync('docs/index.html', 'utf8');

const start = html.indexOf('const MENU = [');
const endMarker = 'const keyOf = (c) =>';
let end = html.indexOf(endMarker);
if (end >= 0) end = html.indexOf('\n', end) + 1; // include the whole keyOf line
if (start < 0 || end <= 0) {
  console.error('EXTRACT_FAILED');
  process.exit(2);
}
const code = html.slice(start, end);
const api = new Function(code + '\n return { rank, enumerate, MENU };')();

const key = (items) => items.map((i) => `${i.code}x${i.qty}`).join('+');

const scenarios = [
  { name: 'B2_D0_B28_Notaste', limits: { burger: [2, 2], drink: [0, 0] }, preferred: [], budget: 2800 },
  { name: 'B2_D0_B28_chicken', limits: { burger: [2, 2], drink: [0, 0] }, preferred: ['chicken'], budget: 2800 },
  { name: 'B2_D0_B30_chicken', limits: { burger: [2, 2], drink: [0, 0] }, preferred: ['chicken'], budget: 3000 },
  { name: 'B2_D1_B30_Notaste', limits: { burger: [2, 2], drink: [1, 1] }, preferred: [], budget: 3000 },
  { name: 'B2_D0_B8_Notaste', limits: { burger: [2, 2], drink: [0, 0] }, preferred: [], budget: 800 }
];

const out = { scenarios: [], enumeration: {} };
for (const s of scenarios) {
  const r = api.rank({ limits: s.limits, preferred: s.preferred, forbidden: [] }, s.budget);
  out.scenarios.push({
    name: s.name,
    accepted: r.accepted ? r.accepted.length : 0,
    rejected: r.rejected ? r.rejected.length : 0,
    picks: (r.picks || []).map((p) => ({ label: p.label, items: key(p.items) })),
    weights: r.weights
  });
}

// Full enumeration for the two shapes the Python side can reproduce exactly.
for (const [name, limits] of [['B2_D0', { burger: [2, 2], drink: [0, 0] }],
                              ['B1_D0', { burger: [1, 1], drink: [0, 0] }],
                              ['B2_D1', { burger: [2, 2], drink: [1, 1] }]]) {
  out.enumeration[name] = api.enumerate(limits).combos.map((c) => key(c.items));
}

console.log(JSON.stringify(out, null, 1));
