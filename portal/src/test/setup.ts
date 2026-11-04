import { vi, expect } from 'vitest';
import '@testing-library/jest-dom';
import * as matchers from 'vitest-axe/matchers';

expect.extend(matchers);

// Mock Canvas getContext for JSDOM / axe-core
if (typeof window !== 'undefined' && window.HTMLCanvasElement) {
  HTMLCanvasElement.prototype.getContext = vi.fn().mockImplementation(() => ({
    fillRect: vi.fn(),
    clearRect: vi.fn(),
    getImageData: vi.fn(() => ({ data: new Uint8ClampedArray(4) })),
    putImageData: vi.fn(),
    createImageData: vi.fn(() => []),
    setTransform: vi.fn(),
    drawImage: vi.fn(),
    save: vi.fn(),
    fillText: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    stroke: vi.fn(),
    translate: vi.fn(),
    scale: vi.fn(),
    rotate: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    measureText: vi.fn(() => ({ width: 0 })),
    transform: vi.fn(),
    rect: vi.fn(),
    clip: vi.fn(),
  }));
}

// Mock maplibre-gl to avoid WebGL errors in JSDOM
vi.mock('maplibre-gl', () => {
  const MockMap = vi.fn(() => ({
    on: vi.fn(),
    off: vi.fn(),
    remove: vi.fn(),
    addControl: vi.fn(),
    flyTo: vi.fn(),
    setCenter: vi.fn(),
    setZoom: vi.fn(),
    getCanvas: vi.fn(() => document.createElement('canvas')),
  }));

  const MockMarker = vi.fn(() => ({
    setLngLat: vi.fn().mockReturnThis(),
    setPopup: vi.fn().mockReturnThis(),
    addTo: vi.fn().mockReturnThis(),
    remove: vi.fn(),
  }));

  const MockPopup = vi.fn(() => ({
    setHTML: vi.fn().mockReturnThis(),
    setText: vi.fn().mockReturnThis(),
    setDOMContent: vi.fn().mockReturnThis(),
  }));

  const MockNavigationControl = vi.fn();

  return {
    default: {
      Map: MockMap,
      Marker: MockMarker,
      Popup: MockPopup,
      NavigationControl: MockNavigationControl,
      setWorkerUrl: vi.fn(),
    },
    Map: MockMap,
    Marker: MockMarker,
    Popup: MockPopup,
    NavigationControl: MockNavigationControl,
    setWorkerUrl: vi.fn(),
  };
});

// Polyfills for JSDOM
if (typeof window !== 'undefined') {
  window.scrollTo = vi.fn();
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
}
