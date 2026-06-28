/** Central Thunderbird add-on update host (all firms). Override with CANARY_TB_UPDATE_BASE_URL. */

export const ADDON_ID = 'canary-file@canarylegal.co.uk'

export const UPDATE_BASE_URL = (
  process.env.CANARY_TB_UPDATE_BASE_URL || 'https://canarylegalsoftware.co.uk/thunderbird'
).replace(/\/+$/, '')

export function xpiFileName(version) {
  return `canary-thunderbird-${version}.xpi`
}

export function xpiPublicUrl(version) {
  return `${UPDATE_BASE_URL}/${xpiFileName(version)}`
}

export function updatesJsonPublicUrl() {
  return `${UPDATE_BASE_URL}/updates.json`
}

export function buildUpdatesManifest(version, xpiBasename = xpiFileName(version)) {
  return {
    addons: {
      [ADDON_ID]: {
        updates: [
          {
            version,
            update_link: `${UPDATE_BASE_URL}/${xpiBasename}`,
          },
        ],
      },
    },
  }
}
