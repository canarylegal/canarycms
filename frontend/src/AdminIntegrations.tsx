import { useState } from 'react'
import { AdminDocuSign } from './AdminDocuSign'
import { AdminHmlr } from './AdminHmlr'
import { AdminSearches } from './AdminSearches'

type IntegrationTab = 'docusign' | 'searches' | 'hmlr'

export function AdminIntegrations({ token }: { token: string }) {
  const [subTab, setSubTab] = useState<IntegrationTab>('docusign')

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="adminTabStrip adminTabStrip--nested" role="tablist" aria-label="Integrations">
        <button
          type="button"
          role="tab"
          aria-selected={subTab === 'docusign'}
          className={`adminTab${subTab === 'docusign' ? ' is-active' : ''}`}
          onClick={() => setSubTab('docusign')}
        >
          DocuSign
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={subTab === 'searches'}
          className={`adminTab${subTab === 'searches' ? ' is-active' : ''}`}
          onClick={() => setSubTab('searches')}
        >
          Searches
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={subTab === 'hmlr'}
          className={`adminTab${subTab === 'hmlr' ? ' is-active' : ''}`}
          onClick={() => setSubTab('hmlr')}
        >
          Land Registry
        </button>
      </div>
      {subTab === 'docusign' ? <AdminDocuSign token={token} /> : null}
      {subTab === 'searches' ? <AdminSearches token={token} /> : null}
      {subTab === 'hmlr' ? <AdminHmlr token={token} /> : null}
    </div>
  )
}
