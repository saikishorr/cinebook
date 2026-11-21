/* eslint-disable react/only-export-components -- small shared admin helpers live together */
import { useEffect, useRef, useState } from 'react'

export const STATUS_LABEL = { CONFIRMED: 'Confirmed', PENDING: 'Pending', CANCELLED: 'Cancelled', FAILED: 'Failed', SCHEDULED: 'Scheduled' }

// A status always carries its word, never colour alone.
export function StatusPill({ status }) {
  return <span className={`status-pill ${String(status).toLowerCase()}`}>{STATUS_LABEL[status] || status}</span>
}

export function Pager({ total, limit, offset, onChange }) {
  if (total <= limit) return null
  const page = Math.floor(offset / limit) + 1
  const pages = Math.ceil(total / limit)
  return (
    <div className="pager">
      <button type="button" className="button print-button" disabled={page <= 1} onClick={() => onChange(offset - limit)}>← Previous</button>
      <span>Page {page} of {pages} · {total} results</span>
      <button type="button" className="button print-button" disabled={page >= pages} onClick={() => onChange(offset + limit)}>Next →</button>
    </div>
  )
}

// Asks for a reason before a destructive action (cancel a booking, cancel a show, block a customer).
export function ReasonDialog({ title, message, confirmLabel, open, busy, onConfirm, onClose }) {
  const ref = useRef(null)
  const [reason, setReason] = useState('')
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) { setReason(''); dialog.showModal() }
    if (!open && dialog.open) dialog.close()
  }, [open])
  return (
    <dialog ref={ref} className="admin-dialog" onClose={onClose} onCancel={onClose}>
      <form method="dialog" onSubmit={event => { event.preventDefault(); if (reason.trim().length >= 3) onConfirm(reason.trim()) }}>
        <h2>{title}</h2>
        <p>{message}</p>
        <label>Reason (saved in the audit log)
          <textarea value={reason} onChange={event => setReason(event.target.value)} rows={3} maxLength={300} autoFocus
                    placeholder="e.g. Customer called the box office" />
        </label>
        <div className="dialog-actions">
          <button type="button" className="button print-button" onClick={onClose}>Keep it</button>
          <button className="button danger-button" disabled={busy || reason.trim().length < 3}>{busy ? 'Working…' : confirmLabel}</button>
        </div>
      </form>
    </dialog>
  )
}

export function useToast() {
  const [toast, setToast] = useState('')
  useEffect(() => {
    if (!toast) return undefined
    const id = setTimeout(() => setToast(''), 4500)
    return () => clearTimeout(id)
  }, [toast])
  return [toast, setToast]
}

export function shortDateTime(value) {
  return value ? new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(new Date(value)) : '—'
}
