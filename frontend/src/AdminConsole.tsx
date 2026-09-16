import { useState } from 'react'
import { AdminAudit } from './AdminAudit'
import { AdminBilling } from './AdminBilling'
import { AdminDeploy } from './AdminDeploy'
import { AdminEmail } from './AdminEmail'
import { AdminDocuSign } from './AdminDocuSign'
import { AdminPortalForms } from './AdminPortalForms'
import { AdminFirmDetails } from './AdminFirmDetails'
import { AdminMatterContacts } from './AdminMatterContacts'
import { AdminMatters } from './AdminMatters'
import { AdminPrecedents } from './AdminPrecedents'
import { AdminSubMenus } from './AdminSubMenus'
import { AdminTasks } from './AdminTasks'
import { AdminUsers } from './AdminUsers'

export { AdminUsers } from './AdminUsers'

export function AdminConsole({ token, refreshMe }: { token: string; refreshMe: () => Promise<void> }) {
  const [tab, setTab] = useState<
    | 'firm'
    | 'users'
    | 'matters'
    | 'billing'
    | 'email'
    | 'docusign'
    | 'portalForms'
    | 'deploy'
    | 'submenus'
    | 'tasks'
    | 'contacts'
    | 'precedents'
    | 'audit'
  >('firm')
  const adminSubtitle =
    tab === 'firm'
      ? 'Trading name, registered name, and firm address for precedent merge codes.'
      : tab === 'email'
      ? 'Org-wide e-mail integration (mailto vs Microsoft 365).'
      : tab === 'docusign'
        ? 'DocuSign integration credentials and send options.'
        : tab === 'portalForms'
          ? 'Portal form templates sent manually to clients.'
          : tab === 'deploy'
        ? 'Deploy, updates, and file storage usage.'
        : tab === 'audit'
        ? 'Activity and audit trail.'
        : tab === 'users'
          ? 'User accounts and permission categories.'
          : tab === 'matters'
            ? 'Matter types and defaults.'
            : tab === 'billing'
              ? 'Billing configuration.'
              : tab === 'submenus'
                ? 'Case sub-menu configuration.'
                : tab === 'tasks'
                  ? 'Task templates and defaults.'
                  : tab === 'contacts'
                    ? 'Matter contact types.'
                    : tab === 'precedents'
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
          <button type="button" role="tab" aria-selected={tab === 'firm'} className={`adminTab${tab === 'firm' ? ' is-active' : ''}`} onClick={() => setTab('firm')}>
            Firm details
          </button>
          <button type="button" role="tab" aria-selected={tab === 'users'} className={`adminTab${tab === 'users' ? ' is-active' : ''}`} onClick={() => setTab('users')}>
            Users
          </button>
          <button type="button" role="tab" aria-selected={tab === 'matters'} className={`adminTab${tab === 'matters' ? ' is-active' : ''}`} onClick={() => setTab('matters')}>
            Matters
          </button>
          <button type="button" role="tab" aria-selected={tab === 'billing'} className={`adminTab${tab === 'billing' ? ' is-active' : ''}`} onClick={() => setTab('billing')}>
            Billing
          </button>
          <button type="button" role="tab" aria-selected={tab === 'email'} className={`adminTab${tab === 'email' ? ' is-active' : ''}`} onClick={() => setTab('email')}>
            E-mail
          </button>
          <button type="button" role="tab" aria-selected={tab === 'docusign'} className={`adminTab${tab === 'docusign' ? ' is-active' : ''}`} onClick={() => setTab('docusign')}>
            DocuSign
          </button>
          <button type="button" role="tab" aria-selected={tab === 'portalForms'} className={`adminTab${tab === 'portalForms' ? ' is-active' : ''}`} onClick={() => setTab('portalForms')}>
            Portal forms
          </button>
          <button type="button" role="tab" aria-selected={tab === 'deploy'} className={`adminTab${tab === 'deploy' ? ' is-active' : ''}`} onClick={() => setTab('deploy')}>
            Deploy
          </button>
          <button type="button" role="tab" aria-selected={tab === 'submenus'} className={`adminTab${tab === 'submenus' ? ' is-active' : ''}`} onClick={() => setTab('submenus')}>
            Sub-Menus
          </button>
          <button type="button" role="tab" aria-selected={tab === 'tasks'} className={`adminTab${tab === 'tasks' ? ' is-active' : ''}`} onClick={() => setTab('tasks')}>
            Tasks
          </button>
          <button type="button" role="tab" aria-selected={tab === 'contacts'} className={`adminTab${tab === 'contacts' ? ' is-active' : ''}`} onClick={() => setTab('contacts')}>
            Contacts
          </button>
          <button type="button" role="tab" aria-selected={tab === 'precedents'} className={`adminTab${tab === 'precedents' ? ' is-active' : ''}`} onClick={() => setTab('precedents')}>
            Precedents
          </button>
          <button type="button" role="tab" aria-selected={tab === 'audit'} className={`adminTab${tab === 'audit' ? ' is-active' : ''}`} onClick={() => setTab('audit')}>
            Audit
          </button>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, marginTop: 12, overflow: 'auto' }}>
        {tab === 'firm' ? (
          <AdminFirmDetails token={token} />
        ) : tab === 'users' ? (
          <AdminUsers token={token} embedded />
        ) : tab === 'matters' ? (
          <AdminMatters token={token} />
        ) : tab === 'billing' ? (
          <AdminBilling token={token} />
        ) : tab === 'email' ? (
          <AdminEmail token={token} onSaved={() => void refreshMe()} />
        ) : tab === 'docusign' ? (
          <AdminDocuSign token={token} />
        ) : tab === 'portalForms' ? (
          <AdminPortalForms token={token} />
        ) : tab === 'deploy' ? (
          <AdminDeploy token={token} />
        ) : tab === 'submenus' ? (
          <AdminSubMenus token={token} />
        ) : tab === 'tasks' ? (
          <AdminTasks token={token} />
        ) : tab === 'contacts' ? (
          <AdminMatterContacts token={token} />
        ) : tab === 'precedents' ? (
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
