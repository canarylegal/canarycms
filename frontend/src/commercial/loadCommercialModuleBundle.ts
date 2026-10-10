import React from 'react'
import ReactDOM from 'react-dom'
import * as jsxRuntime from 'react/jsx-runtime'
import { apiUrl } from '../api'
import type { CommercialModuleBundle } from './commercialModuleTypes'

declare global {
  interface Window {
    React?: typeof React
    ReactDOM?: typeof ReactDOM
    jsxRuntime?: typeof jsxRuntime
    CanaryCommercialModule?: CommercialModuleBundle
  }
}

let loadPromise: Promise<CommercialModuleBundle | null> | null = null

/** Load the commercial package IIFE UI bundle (same-origin via Canary API). */
export function loadCommercialModuleBundle(bundleUrl: string): Promise<CommercialModuleBundle | null> {
  if (typeof window === 'undefined') return Promise.resolve(null)
  if (window.CanaryCommercialModule) return Promise.resolve(window.CanaryCommercialModule)
  if (loadPromise) return loadPromise

  window.React = React
  window.ReactDOM = ReactDOM
  window.jsxRuntime = jsxRuntime

  const src = bundleUrl.startsWith('http')
    ? bundleUrl
    : apiUrl(bundleUrl.startsWith('/') ? bundleUrl : `/${bundleUrl}`)

  loadPromise = new Promise((resolve) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[data-canary-commercial-ui="${src}"]`)
    if (existing && window.CanaryCommercialModule) {
      resolve(window.CanaryCommercialModule)
      return
    }
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.dataset.canaryCommercialUi = src
    script.onload = () => {
      resolve(window.CanaryCommercialModule ?? null)
    }
    script.onerror = () => {
      loadPromise = null
      resolve(null)
    }
    document.head.appendChild(script)
  })
  return loadPromise
}

export function resetCommercialModuleBundleCache() {
  loadPromise = null
  if (typeof window !== 'undefined') {
    delete window.CanaryCommercialModule
  }
}
