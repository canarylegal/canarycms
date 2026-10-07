import React from 'react'
import ReactDOM from 'react-dom'
import * as jsxRuntime from 'react/jsx-runtime'
import { apiUrl } from '../api'
import type { FirmModuleBundle } from './firmModuleTypes'

declare global {
  interface Window {
    React?: typeof React
    ReactDOM?: typeof ReactDOM
    jsxRuntime?: typeof jsxRuntime
    CanaryFirmModule?: FirmModuleBundle
  }
}

let loadPromise: Promise<FirmModuleBundle | null> | null = null

/**
 * Load the firm package IIFE UI bundle (same-origin via Canary API).
 * Host exposes React globals expected by the Vite IIFE build.
 */
export function loadFirmModuleBundle(bundleUrl: string): Promise<FirmModuleBundle | null> {
  if (typeof window === 'undefined') return Promise.resolve(null)
  if (window.CanaryFirmModule) return Promise.resolve(window.CanaryFirmModule)
  if (loadPromise) return loadPromise

  window.React = React
  window.ReactDOM = ReactDOM
  window.jsxRuntime = jsxRuntime

  const src = bundleUrl.startsWith('http')
    ? bundleUrl
    : apiUrl(bundleUrl.startsWith('/') ? bundleUrl : `/${bundleUrl}`)

  loadPromise = new Promise((resolve) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[data-canary-firm-ui="${src}"]`)
    if (existing && window.CanaryFirmModule) {
      resolve(window.CanaryFirmModule)
      return
    }
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.dataset.canaryFirmUi = src
    script.onload = () => {
      resolve(window.CanaryFirmModule ?? null)
    }
    script.onerror = () => {
      loadPromise = null
      resolve(null)
    }
    document.head.appendChild(script)
  })
  return loadPromise
}

/** Clear cached loader (tests / hot remount). */
export function resetFirmModuleBundleCache() {
  loadPromise = null
  if (typeof window !== 'undefined') {
    delete window.CanaryFirmModule
  }
}
