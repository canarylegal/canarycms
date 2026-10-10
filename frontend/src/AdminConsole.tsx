import { useEffect, useState } from 'react'
import { AdminAudit } from './AdminAudit'
import { AdminBilling } from './AdminBilling'
import { AdminDeploy } from './AdminDeploy'
import { AdminEmail } from './AdminEmail'
import { AdminIntegrations } from './AdminIntegrations'
import { AdminPortalForms } from './AdminPortalForms'
import { AdminFirmDetails } from './AdminFirmDetails'
import { AdminMatterContacts } from './AdminMatterContacts'
import { AdminMatters } from './AdminMatters'
import { AdminPrecedents } from './AdminPrecedents'
import { AdminSubMenus } from './AdminSubMenus'
import { AdminTasks } from './AdminTasks'
import { AdminUsers } from './AdminUsers'
import { apiFetch } from './api'
import {
  commercialPackageActive,
  type CommercialPackageStatus,
} from './types/commercial'

export { AdminUsers } from './AdminUsers'

export function AdminConsole({ token, refreshMe }: { token: string; refreshMe: () => Promise<void> }) {
  const [tab, setTab] = useState<
    | 'firm'
    | 'users'
    | 'matters'
    | 'billing'
    | 'email'
    | 'integrations'
    | 'portalForms'
    | 'deploy'
    | 'submenus'
    | 'tasks'
    | 'contacts'
    | 'precedents'
    | 'audit'
  >('firm')
  const [commercial, setCommercial] = useState<CommercialPackageStatus | null>(null)

  useEffect(() => {
    let cancelled = false
    void apiFetch<CommercialPackageStatus>('/commercial-package/status', { token })
      .then((s) => {
        if (!cancelled) setCommercial(s)
      })
      .catch(() => {
        if (!cancelled) setCommercial(null)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const showIntegrations = commercialPackageActive(commercial)
  // Fall back when Integrations is selected but the commercial package is not attached.
  const activeTab = tab === 'integrations' && commercial !== null && !showIntegrations ? 'firm' : tab

  const adminSubtitle =
    activeTab === 'firm'
      ? 'Trading name, registered name, and firm address for precedent merge codes.'
      : activeTab === 'email'
      ? 'Org-wide e-mail integration (mailto vs Microsoft 365).'
      : activeTab === 'integrations'
        ? 'Commercial connectors (DocuSign, Searches, Land Registry).'
        : activeTab === 'portalForms'
          ? 'Portal form templates sent manually to clients.'
          : activeTab === 'deploy'
        ? 'Deploy, updates, and file storage usage.'
        : activeTab === 'audit'
        ? 'Activity and audit trail.'
        : activeTab === 'users'
          ? 'User accounts and permission categories.'
          : activeTab === 'matters'
            ? 'Matter types and defaults.'
            : activeTab === 'billing'
              ? 'Billing configuration.'
              : activeTab === 'submenus'
                ? 'Case sub-menu configuration.'
                : activeTab === 'tasks'
                  ? 'Task templates and defaults.'
                  : activeTab === 'contacts'
                    ? 'Matter contact types.'
                    : activeTab === 'precedents'
                      ? 'Precedent library.'
                      : ''
  return (
    <div
      className="mainMenuShell mainMenuShell--surface"
      style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div className="paneHead">
        <div>
          <h2 style={{ margin: 0 }}>Admin Settings</h2>
          <div className="muted" style={{ marginTop: 4 }}>{adminSubtitle}</div>
        </div>
        <div className="adminTabStrip" role="tablist" aria-label="Admin sections">
          <button type="button" role="tab" aria-selected={activeTab === 'firm'} className={`adminTab${activeTab === 'firm' ? ' is-active' : ''}`} onClick={() => setTab('firm')}>
            Firm details
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'users'} className={`adminTab${activeTab === 'users' ? ' is-active' : ''}`} onClick={() => setTab('users')}>
            Users
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'matters'} className={`adminTab${activeTab === 'matters' ? ' is-active' : ''}`} onClick={() => setTab('matters')}>
            Matters
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'billing'} className={`adminTab${activeTab === 'billing' ? ' is-active' : ''}`} onClick={() => setTab('billing')}>
            Billing
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'email'} className={`adminTab${activeTab === 'email' ? ' is-active' : ''}`} onClick={() => setTab('email')}>
            E-mail
          </button>
          {showIntegrations ? (
            <button type="button" role="tab" aria-selected={activeTab === 'integrations'} className={`adminTab${activeTab === 'integrations' ? ' is-active' : ''}`} onClick={() => setTab('integrations')}>
              Integrations
            </button>
          ) : null}
          <button type="button" role="tab" aria-selected={activeTab === 'portalForms'} className={`adminTab${activeTab === 'portalForms' ? ' is-active' : ''}`} onClick={() => setTab('portalForms')}>
            Portal forms
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'deploy'} className={`adminTab${activeTab === 'deploy' ? ' is-active' : ''}`} onClick={() => setTab('deploy')}>
            Deploy
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'submenus'} className={`adminTab${activeTab === 'submenus' ? ' is-active' : ''}`} onClick={() => setTab('submenus')}>
            Sub-Menus
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'tasks'} className={`adminTab${activeTab === 'tasks' ? ' is-active' : ''}`} onClick={() => setTab('tasks')}>
            Tasks
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'contacts'} className={`adminTab${activeTab === 'contacts' ? ' is-active' : ''}`} onClick={() => setTab('contacts')}>
            Contacts
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'precedents'} className={`adminTab${activeTab === 'precedents' ? ' is-active' : ''}`} onClick={() => setTab('precedents')}>
            Precedents
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'audit'} className={`adminTab${activeTab === 'audit' ? ' is-active' : ''}`} onClick={() => setTab('audit')}>
            Audit
          </button>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, marginTop: 12, overflow: 'auto' }}>
        {activeTab === 'firm' ? (
          <AdminFirmDetails token={token} />
        ) : activeTab === 'users' ? (
          <AdminUsers token={token} embedded />
        ) : activeTab === 'matters' ? (
          <AdminMatters token={token} />
        ) : activeTab === 'billing' ? (
          <AdminBilling token={token} />
        ) : activeTab === 'email' ? (
          <AdminEmail token={token} onSaved={() => void refreshMe()} />
        ) : activeTab === 'integrations' && showIntegrations ? (
          <AdminIntegrations token={token} />
        ) : activeTab === 'portalForms' ? (
          <AdminPortalForms token={token} />
        ) : activeTab === 'deploy' ? (
          <AdminDeploy token={token} />
        ) : activeTab === 'submenus' ? (
          <AdminSubMenus token={token} />
        ) : activeTab === 'tasks' ? (
          <AdminTasks token={token} />
        ) : activeTab === 'contacts' ? (
          <AdminMatterContacts token={token} />
        ) : activeTab === 'precedents' ? (
          <AdminPrecedents token={token} />
        ) : (
          <AdminAudit token={token} embedded />
        )}
      </div>
    </div>
  )
}

export function RecoveryConsole({ token }: { token: string }) {
  return (
    <div
      className="mainMenuShell mainMenuShell--surface"
      style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div className="paneHead">
        <div>
          <h2 style={{ margin: 0 }}>Recovery console</h2>
          <div className="muted" style={{ marginTop: 4 }}>
            User accounts, permission categories, and organisation security policy. No access to cases or firm data.
          </div>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, marginTop: 12, overflow: 'auto' }}>
        <AdminUsers token={token} embedded recoveryMode />
      </div>
    </div>
  )
}
