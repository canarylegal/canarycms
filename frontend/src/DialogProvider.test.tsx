import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { describe, expect, it } from 'vitest'
import { DialogProvider, useDialogs } from './DialogProvider'

function Probe({ onReady }: { onReady: (api: ReturnType<typeof useDialogs>) => void }): ReactElement {
  const api = useDialogs()
  onReady(api)
  return <div>ready</div>
}

describe('DialogProvider queue', () => {
  it('resolves queued confirms in FIFO order without dropping the first promise', async () => {
    const user = userEvent.setup()
    let api: ReturnType<typeof useDialogs> | null = null
    render(
      <DialogProvider>
        <Probe
          onReady={(a) => {
            api = a
          }}
        />
      </DialogProvider>,
    )

    expect(api).toBeTruthy()
    const first = api!.askConfirm({ title: 'First', message: 'one', confirmLabel: 'Yes1' })
    const second = api!.askConfirm({ title: 'Second', message: 'two', confirmLabel: 'Yes2' })

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('First')).toBeInTheDocument()
    expect(screen.queryByText('Second')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Yes1' }))
    await expect(first).resolves.toBe(true)

    expect(await screen.findByText('Second')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Yes2' }))
    await expect(second).resolves.toBe(true)

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('queues an alert behind an open confirm', async () => {
    const user = userEvent.setup()
    let api: ReturnType<typeof useDialogs> | null = null
    render(
      <DialogProvider>
        <Probe
          onReady={(a) => {
            api = a
          }}
        />
      </DialogProvider>,
    )

    const confirm = api!.askConfirm({ title: 'Confirm me', message: 'c', confirmLabel: 'OK confirm' })
    const alert = api!.alert('Alert body', 'Notice')

    expect(await screen.findByText('Confirm me')).toBeInTheDocument()
    expect(screen.queryByText('Alert body')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await expect(confirm).resolves.toBe(false)

    expect(await screen.findByText('Alert body')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'OK' }))
    await expect(alert).resolves.toBeUndefined()
  })

  it('resolves secondary confirm action', async () => {
    const user = userEvent.setup()
    let api: ReturnType<typeof useDialogs> | null = null
    render(
      <DialogProvider>
        <Probe
          onReady={(a) => {
            api = a
          }}
        />
      </DialogProvider>,
    )

    const pending = api!.askConfirmChoice({
      title: 'Revoke?',
      message: 'warn',
      confirmLabel: 'Revoke',
      secondaryLabel: 'Keep',
      cancelLabel: 'Cancel',
    })
    expect(await screen.findByText('Revoke?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Keep' }))
    await expect(pending).resolves.toBe('secondary')
  })
})
