const test = require('node:test');
const assert = require('node:assert/strict');
const D = require('../app/daily.js');
const T = require('../app/tiles.js');
const date = '2026-10-21';
const task = { id: '0123456789abcdef', text: '<script>task</script>', done: false };

test('local date uses the calendar day, including the midnight boundary', () => {
  assert.equal(D.day(new Date(2026, 9, 21, 23, 59, 59)), date);
  assert.equal(D.day(new Date(2026, 9, 22, 0, 0, 0)), '2026-10-22');
});
test('stale phone snapshots and previous-day tasks never leak into today', () => {
  assert.deepEqual(D.forDay({ date, tasks: [task] }, '2026-10-22'), { date: '2026-10-22', tasks: [] });
  const tile = T.items({ today: '2026-10-22', daily: { date, tasks: [task] } }).find(t => t.key === 'daily');
  assert.equal(tile.count, 0);
  assert.deepEqual(tile.rows, []);
  assert.ok(!tile.cleared); // empty lists must remain openable so the first task can be added
});
test('queued phone actions are idempotent and leave unrelated tasks intact', () => {
  const add = { date, action: 'add', id: task.id, text: task.text };
  const first = D.apply(null, add);
  assert.deepEqual(D.apply(first, add), first);
  const second = D.apply(first, { ...add, id: 'fedcba9876543210', text: 'Second task' });
  const checked = D.apply(second, { date, action: 'set', id: task.id, done: true });
  assert.equal(checked.tasks[0].done, true);
  assert.equal(second.tasks[0].done, false);
  assert.equal(D.apply(checked, { date, action: 'remove', id: task.id }).tasks[0].text, 'Second task');
});
test('daily tile shows remaining count and escaped task preview', () => {
  const tile = T.items({ today: date, daily: { date, tasks: [task, { ...task, id: 'fedcba9876543210', done: true }] } }).find(t => t.key === 'daily');
  assert.equal(tile.count, 1);
  assert.match(tile.summary, /1 of 2/);
  const html = T.renderPart(tile, 'list', { w: 400, h: 200 }, {});
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
});
test('daily tile mentions today\'s morning brief, never a stale one', () => {
  const brief = { path: 'daily/2026-10-21-briefing.md', line: 'Quiz at 16:30.' };
  const tile = T.items({ today: date, daily: { date, tasks: [], brief } }).find(t => t.key === 'daily');
  assert.match(tile.summary, /Morning brief ready/);
  assert.deepEqual(tile.rows[0], ['Morning brief', 'Quiz at 16:30.']);
  const stale = T.items({ today: '2026-10-22', daily: { date, tasks: [], brief } }).find(t => t.key === 'daily');
  assert.deepEqual(stale.rows, []);
});
