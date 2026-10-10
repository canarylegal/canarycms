export type CommercialPackageStatus = {
  attached: boolean
  compatible: boolean
  fault: boolean
  package_id: string | null
  package_version: string | null
  label: string | null
  requires_canary: string | null
  canary_version: string
  message: string | null
  detail: string | null
  mounts: string[]
  products: string[]
  loaded: boolean
}

/** True when commercial connectors may be used in the UI. */
export function commercialPackageActive(s: CommercialPackageStatus | null | undefined): boolean {
  return Boolean(s && s.attached && s.compatible && s.loaded)
}

export function commercialHasProduct(
  s: CommercialPackageStatus | null | undefined,
  product: string,
): boolean {
  if (!commercialPackageActive(s)) return false
  return (s!.products || []).includes(product)
}
