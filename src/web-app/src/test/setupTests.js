import '@testing-library/jest-dom';
import { configure } from '@testing-library/react';

// Some views are lazily imported (React.lazy + Suspense). On slow or networked
// workstations module resolution can exceed the 1s Testing Library default, so
// async queries (findBy*/waitFor) get a budget aligned with vitest's testTimeout.
configure({ asyncUtilTimeout: 5000 });

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class IntersectionObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

window.scrollTo = () => {};
globalThis.scrollTo = window.scrollTo;

if (!window.ResizeObserver) {
  window.ResizeObserver = ResizeObserverMock;
}
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = window.ResizeObserver;
}

if (!window.IntersectionObserver) {
  window.IntersectionObserver = IntersectionObserverMock;
}
if (!globalThis.IntersectionObserver) {
  globalThis.IntersectionObserver = window.IntersectionObserver;
}

const originalAnchorClick = window.HTMLAnchorElement.prototype.click;

window.HTMLAnchorElement.prototype.click = function patchedAnchorClick() {
  const href = String(this.getAttribute('href') || this.href || '').trim();
  const download = String(this.getAttribute('download') || this.download || '').trim();

  if (download || href.startsWith('blob:')) {
    if (!Array.isArray(window.__downloadEvents)) {
      window.__downloadEvents = [];
    }
    window.__downloadEvents.push({ href, download });
    return;
  }

  return originalAnchorClick.call(this);
};

beforeEach(() => {
  window.__downloadEvents = [];
});
