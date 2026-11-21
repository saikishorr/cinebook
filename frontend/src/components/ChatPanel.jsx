import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getChatMessages, sendChatMessage } from '../api'

// Phase 3: the CineBook Assistant. The conversation is stored on the server, so it survives a page refresh.
// All rules (what may be answered, limits, refusals) are enforced by the API; this panel only shows the result.
const SAMPLE_QUESTIONS = [
  'What time should I arrive?',
  'Which seats did I book?',
  'Is there parking at the cinema?',
  'How do I cancel my booking?',
]

function timeOf(value) {
  return new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(new Date(value))
}

export default function ChatPanel({ code, firstName }) {
  const [chat, setChat] = useState(null)          // { enabled, messages, remaining_this_hour, max_message_chars }
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState('')      // the question shown while waiting for the reply
  const [error, setError] = useState('')
  const endRef = useRef(null)

  useEffect(() => {
    let active = true
    getChatMessages(code)
      .then(data => { if (active) setChat(data) })
      .catch(requestError => { if (active) setError(requestError.message) })
    return () => { active = false }
  }, [code])

  // Keep the newest message in view.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [chat?.messages.length, pending])

  async function send(question) {
    const message = question.trim()
    if (!message || sending || !chat?.enabled) return
    setSending(true)
    setPending(message)
    setError('')
    setText('')
    try {
      const result = await sendChatMessage(code, message)
      setChat(current => ({
        ...current,
        messages: [...current.messages, result.user_message, result.reply],
        remaining_this_hour: result.remaining_this_hour,
      }))
    } catch (requestError) {
      setError(requestError.message)
      setText(message)                              // give the question back so it is not lost
    } finally {
      setPending('')
      setSending(false)
    }
  }

  const maxChars = chat?.max_message_chars || 500
  const remaining = chat?.remaining_this_hour ?? 0
  const available = Boolean(chat?.enabled)
  const canType = available && !sending && remaining > 0
  const empty = chat && chat.messages.length === 0 && !pending

  return (
    <section className="chat-panel panel" aria-label="Chat assistant">
      <div className="chat-panel-head">
        <span className="chat-avatar" aria-hidden="true">✦</span>
        <div><strong>CineBook Assistant</strong><small>{available ? 'Ask about your booking, showtimes and the cinema' : 'Not available right now'}</small></div>
      </div>

      <div className="chat-messages" aria-live="polite">
        <div className="chat-bubble bot">Hello {firstName}! I can help with your booking, our movies and showtimes, and information about the cinema. What would you like to know?</div>
        {chat?.messages.map(message => (
          <div className={`chat-bubble ${message.role === 'user' ? 'me' : 'bot'} ${message.outcome === 'ERROR' ? 'soft' : ''}`} key={message.id}>
            {message.content}
            <time>{timeOf(message.created_at)}</time>
          </div>
        ))}
        {pending && <div className="chat-bubble me">{pending}</div>}
        {pending && <div className="chat-bubble bot typing" aria-label="The assistant is typing"><i /><i /><i /></div>}
        {empty && available && (
          <div className="chat-suggestions">
            {SAMPLE_QUESTIONS.map(question => <button type="button" key={question} onClick={() => send(question)} disabled={!canType}>{question}</button>)}
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="chat-error" role="alert">{error}</p>}
      {available && remaining <= 5 && <p className="chat-note">{remaining > 0 ? `${remaining} message${remaining === 1 ? '' : 's'} left this hour` : 'Message limit reached for this hour. Please come back later.'}</p>}

      <form className="chat-input" onSubmit={event => { event.preventDefault(); send(text) }}>
        <input value={text} onChange={event => setText(event.target.value)} maxLength={maxChars} disabled={!canType}
               placeholder={!chat && !error ? 'Loading…' : available ? 'Ask about your booking…' : 'The chat assistant is not available right now'}
               aria-label="Your question" autoComplete="off" />
        <button className="button primary" disabled={!canType || !text.trim()}>{sending ? '…' : 'Send'}</button>
      </form>
      <p className="chat-foot">
        {text.length > maxChars * 0.8 && <span>{text.length}/{maxChars} · </span>}
        Answers come from your booking and our <Link to="/help">Help &amp; info</Link> page.
      </p>
    </section>
  )
}
