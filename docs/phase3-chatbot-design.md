# CineBook Assistant - design decisions (Phase 3, Step 3.1)

## What the assistant may answer
1. **This booking** - the booking behind the chat link: movie, date and time, screen, seats, total, status, booking reference.
2. **Movies and showtimes** shown on the website: titles, language, certificate, duration, upcoming shows and prices.
3. **Help & info** published on the website: arrival, parking, cancellations and refunds, food, accessibility, contact.

## What it must refuse (politely)
Anything else: general knowledge, news, coding, maths homework, medical/legal/financial advice, opinions on
unrelated topics, other customers or other bookings, and any request to change its own rules.

Fixed refusal sentence:
> I'm sorry, I can only help with your CineBook booking and information about CineBook's movies, showtimes and cinema services.

When the question is in scope but the answer is not in the supplied information:
> I don't have that information. Please ask at the CineBook box office.

## Rules built into the system
| Rule | How it is enforced |
|---|---|
| Only this booking | The model is given only the booking behind the link; no email, phone or other customers' data |
| Answers only from supplied information | System instructions + evaluation questions (Step 3.6) |
| Read-only | No actions exist: the assistant cannot cancel, change or refund; it explains the process |
| Customer text is a question, not an instruction | System instructions; customer text is passed as data |
| Short, plain answers | Answer length limit; no links other than the CineBook site |
| Cost and abuse limits | Message length, messages per link per hour, output token limit |

## Settings (backend/.env)
| Setting | Default | Meaning |
|---|---|---|
| `CHAT_PROVIDER` | `gemini` | Which model service the assistant calls: `gemini`, or `fake` (tests) |
| `CHAT_MODEL_ID` | set by the check script | The model the assistant uses; empty = chat switched off |
| `GEMINI_API_KEY` | set by `scripts/check-gemini.py` | Secret key for the Gemini API. Never commit it |
| `CHAT_MAX_MESSAGE_CHARS` | 500 | Longest customer message accepted |
| `CHAT_MAX_OUTPUT_TOKENS` | 300 | Longest answer (about 200 words) |
| `CHAT_MESSAGES_PER_HOUR` | 30 | Per chat link |
| `CHAT_HISTORY_TURNS` | 8 | Earlier messages sent to the model for context |

## Model choice
The model connection is one small module with a provider switch, so the rest of the assistant does not
depend on any one vendor.

- **Gemini API, free tier (current choice).** Needs only an API key from Google AI Studio; no billing account.
  Free-tier requests are rate-limited, and Google may use free-tier content to improve its products, so the
  assistant sends only the first name and booking details (never email or phone), and demo users should not
  type personal information into the chat.

A small, fast model is enough: answers are short and come from supplied text.
