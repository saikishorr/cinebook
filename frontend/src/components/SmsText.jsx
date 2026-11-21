// Shows an SMS body with any web address turned into a tappable link.
const URL_PATTERN = /(https?:\/\/[^\s]+)/g

export default function SmsText({ text }) {
  return text.split(URL_PATTERN).map((part, index) =>
    index % 2 === 1
      ? <a key={index} href={part} className="sms-link">{part}</a>
      : <span key={index}>{part}</span>,
  )
}
