import assert from 'node:assert/strict';
import test from 'node:test';

import { isChunkLoadFailure, attemptChunkReload } from '../lib/chunk-recovery.ts';

function fakeStore() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => { data.set(key, value); },
  };
}

test('recognizes actual Next dynamic-chunk error but not unrelated React errors', () => {
  assert.equal(isChunkLoadFailure(new Error('Failed to load chunk /mini-app/_next/static/chunks/example.js from module 87760')), true);
  assert.equal(isChunkLoadFailure(Object.assign(new Error('Loading chunk 42 failed.'), { name: 'ChunkLoadError' })), true);
  assert.equal(isChunkLoadFailure(new Error('Invalid Telegram initData')), false);
});

test('reloads only once in bounded window and then permits recovery', () => {
  const store = fakeStore();
  const error = new Error('Failed to load chunk /mini-app/_next/static/chunks/example.js');
  let reloads = 0;
  const reload = () => { reloads += 1; };
  assert.equal(attemptChunkReload(error, store, reload, 1000000), true);
  assert.equal(attemptChunkReload(error, store, reload, 1000001), false);
  assert.equal(reloads, 1);
  assert.equal(attemptChunkReload(error, store, reload, 1300001), true);
  assert.equal(reloads, 2);
});

test('never reloads unrelated error or when storage is unavailable', () => {
  const store = fakeStore();
  let reloads = 0;
  const reload = () => { reloads += 1; };
  assert.equal(attemptChunkReload(new Error('Invalid Telegram initData'), store, reload, 1000000), false);
  assert.equal(attemptChunkReload(new Error('Failed to load chunk x'), null, reload, 1000000), false);
  assert.equal(reloads, 0);
});
