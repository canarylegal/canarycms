import { useState } from 'react'
import { AdminDocuSign } from './AdminDocuSign'

type IntegrationTab = 'docusign'

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
      </div>
      {subTab === 'docusign' ? <AdminDocuSign token={token} /> : null}
    </div>
  )
}
