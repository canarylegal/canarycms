/** Install product chrome from ``GET /brand/public`` (env-only; forks). */

import { apiFetch } from './api'

export type BrandPublic = {
  product_name: string
  vendor_url: string
}

let cached: BrandPublic = {
  product_name: 'Canary',
  vendor_url: 'https://canarylegalsoftware.co.uk',
}

let loadPromise: Promise<BrandPublic> | null = null

export function getProductName(): string {
  return cached.product_name || 'Canary'
}

export function getVendorUrl(): string {
  return cached.vendor_url || 'https://canarylegalsoftware.co.uk'
}

/** Load once; safe to call from multiple components. */
export function ensureBrandConfig(): Promise<BrandPublic> {
  if (loadPromise) return loadPromise
  loadPromise = apiFetch<BrandPublic>('/brand/public')
    .then((data) => {
      cached = {
        product_name: (data.product_name || '').trim() || 'Canary',
        vendor_url: (data.vendor_url || '').trim() || cached.vendor_url,
      }
      return cached
    })
    .catch(() => cached)
  return loadPromise
}
