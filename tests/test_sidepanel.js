const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function panel(fetchImpl, scriptImpl) {
  const nodes = new Map();
  const location = {href: 'https://example.org/'};
  const documentElement = {outerHTML: '<html>synthetic</html>'};
  const timers = new Map(); let nextTimer = 1;
  function safeElement() {
    const value = {};
    Object.defineProperty(value, 'innerHTML', {set() {throw new Error('unsafe HTML assignment');}});
    return value;
  }
  function element(id) {
    if (!nodes.has(id)) nodes.set(id, Object.assign(safeElement(), {value: '', checked: false, style: {}, children: [], listeners: {},
      addEventListener(event, callback) { this.listeners[event] = callback; },
      appendChild(child) { this.children.push(child); }, replaceChildren() { this.children = []; }}));
    return nodes.get(id);
  }
  element('maxDepth').value = '3';
  const errors = [], calls = [];
  const context = vm.createContext({Error, AbortController, Number, Array,
    document: {getElementById: element, createElement: safeElement, documentElement}, location,
    chrome: {tabs: {query: async () => [{id: 1, url: 'https://example.org/'}]},
      scripting: {executeScript: async options => {
        assert.equal(options.target.tabId, 1);
        return scriptImpl ? scriptImpl(options) : [{result: options.func()}];
      }}},
    fetch: async (...args) => { calls.push(args); return fetchImpl(...args); },
    setTimeout: (callback, delay) => {const id = nextTimer++; timers.set(id, {callback, delay}); return id;},
    clearTimeout: id => timers.delete(id), setInterval: () => 1, alert() {},
    console: {error: (...args) => errors.push(args)}
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../chrome-plugin/sidepanel.js'), 'utf8'), context);
  return {context, nodes, calls, errors, element, location, documentElement, timers,
    flush: () => new Promise(resolve => setImmediate(resolve)),
    click: () => element('saveBtn').listeners.click()};
}
const status = {ok: true, json: async () => ({crawl_active: false, saved_urls: []})};

test('HTTP rejection is visible and does not claim a saved page', async () => {
  const p = panel(async url => url.endsWith('/list') ? status : {ok: false, status: 409});
  await p.flush(); await p.click();
  assert.match(p.element('feedback').textContent, /409/);
  assert.doesNotMatch(p.element('feedback').textContent, /Page saved/);
  assert.ok(p.errors.length > 0);
  assert.equal(p.element('saveBtn').disabled, false);
});

test('DOM capture rejection is handled before any save request', async () => {
  const p = panel(async () => status, async () => { throw new Error('capture denied'); });
  await p.flush(); await p.click();
  assert.equal(p.calls.filter(([url]) => url.endsWith('/save')).length, 0);
  assert.match(p.element('feedback').textContent, /capture denied/);
});

test('negative depth prevents submission and saved URLs render as text', async () => {
  const hostile = '<img src=x onerror=alert(1)>';
  const p = panel(async () => ({ok: true, json: async () => ({crawl_active: false, saved_urls: [hostile]})}));
  await p.flush();
  assert.equal(p.element('linkList').children[0].textContent, hostile);
  p.element('maxDepth').value = '-1'; await p.click();
  assert.equal(p.calls.filter(([url]) => url.endsWith('/save')).length, 0);
  assert.match(p.element('feedback').textContent, /nonnegative/);
});

test('concurrent clicks issue only one write and successful save is displayed', async () => {
  let complete;
  const p = panel(async url => url.endsWith('/list') ? status : new Promise(resolve => {complete = resolve;}));
  await p.flush(); const first = p.click(); await p.flush(); await p.click();
  assert.equal(p.calls.filter(([url]) => url.endsWith('/save')).length, 1);
  complete({ok: true, json: async () => ({status: 'ok'})}); await first;
  assert.equal(p.element('feedback').textContent, 'Page saved.');
  assert.equal(p.element('saveBtn').disabled, false);
});

test('background panel rejection is observed', async () => {
  let callback; const errors = [];
  const context = vm.createContext({chrome: {action: {onClicked: {addListener(fn) {callback = fn;}}},
    sidePanel: {open: () => Promise.reject(new Error('synthetic'))}},
    console: {error: (...args) => errors.push(args)}});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../chrome-plugin/background.js'), 'utf8'), context);
  callback({windowId: 1}); await new Promise(resolve => setImmediate(resolve));
  assert.equal(errors.length, 1); assert.match(errors[0][0], /panel/i);
});


test('capture URL and HTML remain paired after tab navigation', async () => {
  const p = panel(async () => status);
  await p.flush(); p.location.href = 'https://example.org/new'; p.documentElement.outerHTML = '<h1>new</h1>';
  await p.click();
  const call = p.calls.find(([url]) => url.endsWith('/save'));
  const payload = JSON.parse(call[1].body);
  assert.equal(payload.url, 'https://example.org/new');
  assert.equal(payload.html, '<h1>new</h1>');
});


test('request timeout aborts the write and restores controls', async () => {
  const p = panel(async (url, options) => url.endsWith('/list') ? status : new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('request timed out')), {once: true});
  }));
  await p.flush(); const click = p.click(); await p.flush();
  const timeout = [...p.timers.values()].find(timer => timer.delay === 10000);
  assert.ok(timeout); timeout.callback(); await click;
  assert.match(p.element('feedback').textContent, /timed out/);
  assert.equal(p.element('saveBtn').disabled, false);
  assert.ok(![...p.timers.values()].some(timer => timer.delay === 10000));
});

test('malformed list data cannot mutate saved links', async () => {
  const p = panel(async () => ({ok: true, json: async () => ({crawl_active: true, saved_urls: 'bad'})}));
  await p.flush();
  assert.match(p.element('feedback').textContent, /invalid status/);
  assert.equal(p.element('linkList').children.length, 0);
});
