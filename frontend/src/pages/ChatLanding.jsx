import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getChatLink } from '../api'
import ChatPanel from '../components/ChatPanel'
import Shell from '../components/Shell'
import { formatDate, formatTime, money } from '../utils/format'
import { useDocumentTitle } from '../utils/hooks'

// The page opened from the link in the booking SMS: the booking on the left, the chat assistant on the right.
export default function ChatLanding() {
  const { code } = useParams()
  useDocumentTitle('Chat with CineBook')
  const [link, setLink] = useState(null)
  const [problem, setProblem] = useState(null)

  useEffect(() => {
    let active = true
    getChatLink(code)
      .then(data => { if (active) setLink(data) })
      .catch(error => { if (active) setProblem({ status: error.status, message: error.message }) })
    return () => { active = false }
  }, [code])

  if (problem) {
    const title = problem.status === 410 ? 'This chat link has been switched off'
      : problem.status === 404 ? 'This chat link is not valid' : 'We couldn’t open this chat'
    const text = problem.status === 404 || problem.status === 410
      ? 'Please check the link in your SMS, or contact the cinema with your booking reference.'
      : problem.message
    return (
      <Shell>
        <div className="state-panel">
          <span className="state-icon">!</span>
          <h1>{title}</h1>
          <p>{text}</p>
          <Link className="button primary" to="/">Go to CineBook</Link>
        </div>
      </Shell>
    )
  }

  if (!link) {
    return <Shell><div className="state-panel pending-panel"><span className="pending-spinner" aria-hidden="true" /><h1>Opening your chat…</h1></div></Shell>
  }

  return (
    <Shell>
      <div className="chat-landing">
        <section className="chat-booking panel">
          <span className="eyebrow">YOUR BOOKING · {link.booking_ref}</span>
          <h1>Hi {link.first_name}<span className="accent">.</span></h1>
          <p className="chat-intro">Here are your booking details. Ask us anything about your visit.</p>
          <h2 className="ticket-movie">{link.movie_title}</h2>
          <div className="ticket-details">
            <div><small>DATE</small><strong>{formatDate(link.start_time)}</strong></div>
            <div><small>TIME</small><strong>{formatTime(link.start_time)}</strong></div>
            {link.cinema_name && <div><small>CINEMA</small><strong>{link.cinema_name}{link.cinema_area ? `, ${link.cinema_area}` : ''}</strong></div>}
            <div><small>SCREEN</small><strong>{link.screen_name}</strong></div>
            <div><small>LANGUAGE</small><strong>{link.movie_language}</strong></div>
            <div><small>SEATS</small><strong>{link.seats.join(' · ') || '—'}</strong></div>
            <div><small>TOTAL</small><strong>{money(link.total_amount)}</strong></div>
          </div>
          <p className={`chat-status ${link.status === 'CONFIRMED' ? 'ok' : ''}`}>Booking status: {link.status}</p>
        </section>

        <ChatPanel code={code} firstName={link.first_name} />
      </div>
    </Shell>
  )
}
