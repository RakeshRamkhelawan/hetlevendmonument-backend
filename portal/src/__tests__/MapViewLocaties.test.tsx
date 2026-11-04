import { describe, it, expect } from 'vitest';
import { naarFeatures } from '../pages/MapView';
import type { FoundationContentListItem } from '../types';

const item = (id: number, lat: number | null, lng: number | null, category = 'verhalen'): FoundationContentListItem =>
  ({
    id,
    title: `Verhaal ${id}`,
    summary: null,
    creator_name: null,
    is_anonymous: false,
    language: 'nl',
    content_type: 'story',
    status: 'approved',
    visibility: 'public',
    file_url: null,
    file_mime: null,
    file_size_bytes: null,
    lat,
    lng,
    location_name: null,
    category,
    created_at: '2026-11-02T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
  }) as FoundationContentListItem;

describe('Kaart: alle locaties uit de openbare lijst', () => {
  it('neemt alleen items met een locatie mee, als [lng, lat]', () => {
    const features = naarFeatures([item(1, 5.85, -55.2), item(6, null, null, 'educatie'), item(4, 12.36, -69.15)]);
    expect(features.map((f) => f.properties.id)).toEqual([1, 4]);
    expect(features[0].geometry.coordinates).toEqual([-55.2, 5.85]);
    expect(features[1].properties.category).toBe('verhalen');
  });

  it('houdt punten ver uit elkaar samen (Suriname, Curacao en Vlaardingen)', () => {
    const features = naarFeatures([item(1, 5.85, -55.2), item(4, 12.36, -69.15), item(5, 51.9, 4.34)]);
    const lngs = features.map((f) => f.geometry.coordinates[0]);
    expect(Math.max(...lngs) - Math.min(...lngs)).toBeGreaterThan(70);
  });
});
