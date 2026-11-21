import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Shell from '../components/Shell'
import { useDocumentTitle } from '../utils/hooks'

// Find a booking again from its reference (e.g. BK7Q2M9X), as printed on the ticket, email and SMS.
export default function FindBooking() {
  const navigate = useNavigate()
  const [reference, setReference] = useState('')
  const [error, setError] = useState('')
  useDocumentTitle('Find my booking')

  function submit(event) {
    event.preventDefault()
    const ref = reference.replace(/\s/g, '').toUpperCase()
    if (!/^[A-Z0-9]{6,12}$/.test(ref)) {
      setError('Enter the booking reference from your ticket or email, for example BK7Q2M9X.')
      return
    }
    navigate(`/booking/${ref}`)
  }

  return (
    <Shell>
      <div className="state-panel find-booking">
        <span className="state-icon">✦</span>
        <span className="eyebrow">MY BOOKING</span>
        <h1>Find your booking</h1>
        <p>Enter the booking reference from your confirmation page, email or SMS.</p>
        <form className="find-form" onSubmit={submit} noValidate>
          <input value={reference} onChange={event => { setReference(event.target.value); setError('') }}
                 placeholder="e.g. BK7Q2M9X" aria-label="Booking reference" autoComplete="off"
                 autoCapitalize="characters" spellCheck="false" maxLength={16} aria-invalid={Boolean(error)} />
          <button className="button primary">Find booking</button>
        </form>
        {error && <small className="find-error" role="alert">{error}</small>}
      </div>
    </Shell>
  )
}
