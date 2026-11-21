Build the customer-facing movie ticket booking website for my existing React + Vite application in `frontend/`.

The Python FastAPI backend is in `backend/` and runs at:

`http://127.0.0.1:8000`

## IMPORTANT — BEFORE WRITING FRONTEND CODE

First inspect `backend/app/` thoroughly, including:

* routers
* models
* schemas
* API endpoint definitions
* response models
* request models
* seat/show/hold structures

Use the **EXACT endpoint paths, HTTP methods, request JSON field names, and response JSON field names exposed by the backend**.

Do NOT guess API structures.

Do NOT modify anything inside:

* `backend/`
* `db/`

Only modify/create files inside `frontend/`.

---

# 1. PRODUCT VISION

The application is called:

# CineBook

This should NOT look like a basic student CRUD project.

Design it like a polished, modern movie-ticketing product comparable in visual quality to a premium cinema booking website.

The visual experience should feel:

* cinematic
* premium
* modern
* immersive
* trustworthy
* elegant
* fast
* easy to understand

Think:

**Netflix + BookMyShow + modern SaaS design**

but do NOT copy any specific site's layout or branding.

The UI should immediately communicate:

> "This is a professional movie-ticket booking platform."

Prioritize excellent visual hierarchy, whitespace, typography, cards, subtle animation, responsive behavior and clear booking states.

---

# 2. VISUAL DESIGN SYSTEM

Create a consistent visual language throughout the application.

## Overall aesthetic

Use a dark cinematic theme as the primary visual style.

Suggested direction:

* deep charcoal / near-black background
* slightly lighter dark surfaces
* warm amber/gold accent for important actions
* subtle gradients
* soft shadows
* thin borders
* rounded cards
* high contrast typography

Avoid making everything pure black.

Use layered dark surfaces so the interface has depth.

For example:

* page background: very dark charcoal
* cards: slightly lighter charcoal
* elevated elements: another slightly lighter surface
* borders: subtle low-opacity borders
* primary accent: cinematic amber/gold

Use Tailwind CSS classes rather than creating a large custom CSS framework.

Do not hard-code colors everywhere. Establish a small consistent palette.

---

# 3. TYPOGRAPHY

Use a modern, highly readable typography hierarchy.

Large cinematic headings for page titles.

Examples:

Movies page:

> Now Showing

Subheading:

> Catch the latest movies playing near you.

Showtimes:

> Choose your showtime

Seat selection:

> Pick your seats

Checkout:

> Complete your booking

Use:

* large bold headings
* medium-weight section headings
* readable body text
* small muted metadata

Avoid excessive uppercase text.

---

# 4. HEADER

Create a polished responsive header.

Desktop:

* CineBook logo/name on the left
* subtle cinema-inspired icon next to CineBook
* navigation/context on the right where useful

Mobile:

* compact header
* CineBook logo
* clean spacing

The CineBook logo should link to `/`.

Header should remain visually consistent across every page.

Use a subtle translucent/glass effect if appropriate:

* semi-transparent dark background
* backdrop blur
* thin bottom border

Do not make the header excessively tall.

---

# 5. GLOBAL UX PRINCIPLES

Every page must have:

* loading state
* error state
* empty state where appropriate
* responsive layout
* accessible buttons
* visible hover states
* visible disabled states
* keyboard-friendly controls

API errors must display the actual error message returned by the API.

Avoid ugly browser-default alerts.

Use polished inline error banners/cards.

For loading:

Prefer skeleton loaders over a simple "Loading..." wherever practical.

Create small reusable components such as:

* `LoadingState`
* `ErrorState`
* `EmptyState`
* `Button`
* `Badge`
* `MovieCard`
* `ShowtimeButton`
* `Seat`
* `Header`

Keep components small and beginner-friendly.

---

# 6. MOVIES PAGE

Route:

`/`

Page title:

**Now Showing**

Subtitle:

**Find your next movie experience.**

Display movies in a responsive grid.

Desktop:

* 4 cards per row where space allows

Tablet:

* 2–3 cards

Mobile:

* 1–2 cards depending on screen width

Each movie card should feel premium.

## Movie card

Include:

* movie poster if the API provides one
* otherwise create an attractive cinematic poster placeholder
* title
* language
* certificate
* duration
* short description
* "View Showtimes" affordance

If the backend does NOT provide poster URLs, do not invent API fields.

Instead create visually attractive placeholder artwork based only on available movie information.

NOTE: At present every movie's `poster_url` is null, so the generated placeholder artwork will be used for every movie. Still render the real poster if a movie ever has a non-null `poster_url`, and fall back to the placeholder if that image fails to load.

Cards should have:

* rounded corners
* subtle border
* shadow
* hover elevation
* slight image zoom on hover
* gradient overlay where appropriate

The entire card should be clickable.

On hover:

* card subtly lifts
* poster scales slightly
* CTA becomes more prominent

Do not overdo animation.

---

# 7. MOVIE DETAILS / SHOWTIMES PAGE

Route:

`/movies/:movieId`

Create a strong movie header section.

If poster information exists:

Use a large poster on the left and movie information on the right.

Display:

* title
* language
* certificate
* duration
* description

Then display:

## Choose your showtime

Group shows by date.

Example:

**Mon, 28 Sep**

Under each date, show showtime cards/buttons.

Each showtime should display:

**6:00 PM**

Screen name

`from ₹250`

Use Asia/Kolkata for all displayed dates/times.

Do NOT simply display raw ISO timestamps.

Use JavaScript's `Intl.DateTimeFormat` appropriately.

Showtime buttons should feel like selectable cinema schedule cards.

Example visual hierarchy:

6:00 PM
Screen 2
from ₹250

Hover:

* accent border
* subtle glow
* slight lift

Clicking navigates to:

`/shows/:showId`

Include a clear back/navigation affordance.

---

# 8. SEAT SELECTION PAGE

Route:

`/shows/:showId`

This is one of the most important screens.

Make it feel like a premium cinema seat-selection experience.

At the top show:

Movie Title

Screen 2

Mon, 28 Sep · 6:00 PM

IMPORTANT: The seat-map endpoint (`GET /shows/{showId}/seats`) may not include the movie title, date or time. For this header, ALSO call the single-show endpoint (`GET /shows/{showId}`) and combine the two responses. Load both in parallel.

## Existing hold banner

If `sessionStorage` contains an active hold for the show being viewed, show a small banner above the seat map:

> You have seats on hold — **Continue to checkout**

linking to `/checkout/{hold_id}`. Store enough in `sessionStorage` (hold_id and show_id) to know which show the hold belongs to.

Note that the user's own held seats will appear as HELD on the seat map (the backend does not know who is viewing). That is expected; the banner explains it.

Then create a visually prominent:

# SCREEN

bar.

The screen should look like a cinema screen rather than a generic rectangle.

For example:

* curved/slightly rounded shape
* subtle glow
* gradient
* "SCREEN" label
* visual perspective if it can be achieved cleanly with CSS

Do not use an SVG image unless necessary.

---

# 9. SEAT MAP

Seats must be grouped by:

`row_label`

and sorted by:

`seat_number`

Show row labels clearly on the left.

Example:

A   ○ ○ ○ ○ ○ ○ ○

B   ○ ○ ○ ○ ○ ○ ○

C   ○ ○ ● ● ○ ○ ○

Use CSS grid/flex rather than complicated absolute positioning unless required by the backend structure.

Seat size must remain usable on mobile.

The seat map should horizontally scroll if required on very small screens rather than becoming unusably compressed.

---

# 10. SEAT STATES

Clearly distinguish:

### AVAILABLE

* dark surface
* visible outline
* accent hover
* clickable

### SELECTED BY ME

* solid accent color
* strong contrast
* subtle glow
* clearly different from available

### HELD BY OTHER USERS

* grey
* muted
* not clickable

### BOOKED

* dark/disabled
* visually unavailable
* not clickable

### PREMIUM

Premium seats must be visually distinct.

For example:

* subtle gold border
* premium badge/icon
* slightly different styling

Create a clear legend:

○ Available

● Selected

■ Premium

▣ Held

✕ Booked

The legend should be compact and easy to understand.

Do not rely only on color to communicate state.

---

# 11. SEAT SELECTION SUMMARY

When seats are selected, show a sticky booking summary on desktop.

For example:

## Your selection

A5 · A6 · A7

3 seats

Total

₹750

[ Hold Seats ]

On mobile, the summary can become a sticky bottom panel.

The summary should remain visible while scrolling.

Maximum selection:

**10 seats**

If the user attempts to select an 11th seat, show a small friendly message such as:

> You can select up to 10 seats.

Do not use a browser alert.

---

# 12. HOLD SEATS

The button:

**Hold Seats**

must call:

`POST /shows/{showId}/holds`

Use the EXACT request JSON structure discovered from the backend.

On success:

1. read `hold_id`
2. save it in `sessionStorage`
3. navigate to:

`/checkout/{hold_id}`

On HTTP 409:

Display:

> Some of those seats were just taken by someone else.

Then:

* clear current selection
* reload the seat map

Make this state visually clear but not alarming.

On HTTP 503:

Display:

> Seat holds are temporarily unavailable. Please try again in a moment.

Keep the user's selection so they can simply try again.

For any other error, show the API's `detail` message.

---

# 13. AUTOMATIC SEAT REFRESH

Refresh the seat map automatically every:

**10 seconds**

Important:

Do NOT reset the user's current selection on every refresh.

Preserve selected seats when they remain available.

If one of the user's selected seats becomes unavailable:

* automatically remove it from selection
* show a small non-blocking message

Example:

> A6 is no longer available and was removed from your selection.

Clean up intervals when the component unmounts.

---

# 14. CHECKOUT PAGE

Route:

`/checkout/:holdId`

This page should feel like the final step of a real booking flow.

Create a clear two-column layout on desktop.

Left:

## Booking details

* movie
* show
* screen
* date
* time
* selected seats

Right:

## Order summary

* seats
* total
* countdown

On mobile stack these sections vertically.

IMPORTANT: The hold endpoint (`GET /holds/{holdId}`) may only return the `show_id` and seat details. To show the movie title, screen, date and time in "Booking details", ALSO fetch the show with `GET /shows/{show_id}` after the hold has loaded.

---

# 15. HOLD COUNTDOWN

Load the hold using:

`GET /holds/{holdId}`

Use:

`seconds_remaining`

Create a highly visible countdown.

Example:

**Hold expires in**

`04:42`

Holds last 5 minutes (the backend setting `HOLD_SECONDS=300`), so the countdown will usually start at around `05:00`. Always use the `seconds_remaining` value from the API rather than assuming a fixed length.

Update every second.

When less than 60 seconds remain, make the countdown visually more urgent (for example, a warmer colour), without being alarming.

Format:

`mm:ss`

When countdown reaches zero OR hold status is `EXPIRED`:

Replace checkout content with a polished expired state.

Example:

# Your hold has expired

Those seats have been released and are available for other customers.

Button:

**Choose seats again**

This should take the user back to the appropriate seat map.

Do not allow payment after expiry.

---

# 16. CUSTOMER DETAILS FORM

Create:

Full name
Email
Phone

Requirements:

* full name required
* email required
* proper email validation
* phone optional

Use clean form styling.

Labels must always be visible.

Show validation errors inline.

Do not rely only on HTML browser validation.

Use clear focus states.

---

# 17. CANCEL HOLD

Button:

**Cancel and release seats**

Calls:

`DELETE /holds/{holdId}`

On success:

1. clear the hold from `sessionStorage`
2. return to the relevant seat map
3. show a small toast such as "Your seats have been released."

Also clear the hold from `sessionStorage` when the hold expires or is not found (404).

Make this a secondary/destructive action, visually distinct from Pay.

---

# 18. PAY BUTTON

Create a large premium primary button:

**Pay ₹1,250**

The amount must be dynamically calculated.

The Pay button must currently be:

**DISABLED**

Under it display:

> Payment and booking confirmation will be added in the next step.

Make the disabled state visually intentional rather than looking broken.

---

# 19. 404 HOLD

If:

`GET /holds/{holdId}`

returns HTTP 404:

Display:

# Booking session not found

> This booking session may have expired or no longer exists.

Button:

**Back to movies**

Link to `/`.

Do not show a raw stack trace or technical error.

---

# 20. MONEY FORMATTING

Always format money using:

```javascript
new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR'
})
```

The API may return prices as strings.

Convert numeric strings safely before calculations.

Never manually concatenate:

`₹ + price`

---

# 21. API LAYER

Create:

`src/api.js`

It should contain one small reusable fetch helper using:

`VITE_API_URL`

The helper must:

* make the request
* parse JSON
* detect HTTP failures
* extract the API's `detail`
* throw an Error containing the detail message AND HTTP status

Export one function per backend endpoint actually used by the application.

IMPORTANT:

Use the endpoint paths and JSON fields discovered from `backend/app`.

Do not invent endpoint names or field names.

---

# 22. ROUTING

Use React Router with:

```text
/                    Movies
/movies/:movieId     Showtimes
/shows/:showId       Seat map
/checkout/:holdId    Checkout
*                    Page not found
```

Use `BrowserRouter`.

Create a simple but polished Page Not Found screen.

Example:

# Page not found

> Looks like this scene isn't in our movie.

Button:

**Back to CineBook**

---

# 23. TAILWIND V4

Tailwind CSS v4 is already installed.

Update `vite.config.js` to include:

`@tailwindcss/vite`

Replace:

`src/index.css`

with:

```css
@import "tailwindcss";
```

Remove Vite starter content including:

* `App.css`
* starter logos
* counter/demo code
* default Vite styles

Do not leave any Vite starter UI behind.

---

# 24. ENVIRONMENT VARIABLES

Create:

`frontend/.env`

containing:

```text
VITE_API_URL=http://127.0.0.1:8000
```

Create:

`frontend/.env.example`

containing:

```text
VITE_API_URL=http://127.0.0.1:8000
```

Make sure:

`.env`

is ignored by git.

Do not expose secrets in frontend code.

---

# 25. RESPONSIVE DESIGN

The site must look excellent at:

* 1440px desktop
* 1280px laptop
* 1024px tablet
* 768px tablet
* 390px mobile
* 375px mobile

Do not simply shrink the desktop UI.

Adapt layouts intelligently.

Examples:

Desktop seat map:

Seat map + sticky booking summary

Mobile:

Seat map + sticky bottom selection bar

Desktop checkout:

Two columns

Mobile:

Single column

---

# 26. ANIMATION & MICRO-INTERACTIONS

Use subtle animations throughout.

Examples:

* page content fade/slide in
* card hover elevation
* poster image zoom
* button hover transitions
* seat selection animation
* countdown transition
* skeleton shimmer
* toast/message appearance

Keep animations fast and professional.

Avoid:

* excessive bouncing
* flashy animations
* distracting transitions
* animations that interfere with booking

Prefer 150–300ms transitions.

Respect `prefers-reduced-motion` where practical.

---

# 27. CINEMATIC DETAILS

Add tasteful details that make the product feel premium.

Possible examples:

* subtle radial background gradients
* cinematic glow around important elements
* very subtle grain/noise effect if achievable without external assets
* gradient overlays on movie cards
* tiny film/cinema icons (built with inline SVG or simple Unicode characters)
* elegant section dividers
* premium badges
* subtle glass surfaces

These should remain restrained.

The UI should feel sophisticated, not like a gaming website.

## No external assets

Use only system fonts (for example a `font-family` stack such as `ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif`).

Do NOT load external fonts, icon libraries, images or CDNs, and do NOT add new npm packages. Build icons with inline SVG or Unicode characters.

This keeps the site self-contained, with no extra dependencies.

---

# 28. TOASTS / NOTIFICATIONS

Create a lightweight reusable notification/toast mechanism for transient messages.

Use it for:

* seat becoming unavailable
* maximum 10 seats
* hold conflicts
* successful cancellation
* other useful transient feedback

Do not use `alert()`.

---

# 29. ACCESSIBILITY

Ensure:

* buttons have meaningful labels
* sufficient contrast
* keyboard focus states
* disabled seats cannot receive interaction
* form inputs have labels
* seat buttons have accessible labels

Example:

`A5, available, regular`

or:

`A6, selected, premium`

---

# 30. FILE STRUCTURE

Prefer a clean structure such as:

```text
frontend/
  .env
  .env.example
  vite.config.js

  src/
    api.js
    main.jsx
    App.jsx
    index.css

    components/
      Header.jsx
      MovieCard.jsx
      ShowtimeButton.jsx
      Seat.jsx
      SeatLegend.jsx
      BookingSummary.jsx
      Countdown.jsx
      LoadingState.jsx
      ErrorState.jsx
      EmptyState.jsx
      Toast.jsx

    pages/
      Movies.jsx
      Showtimes.jsx
      SeatMap.jsx
      Checkout.jsx
      NotFound.jsx
```

You may adjust the structure if the existing application already has a sensible structure.

Do not create unnecessary abstraction.

Keep components small enough for a beginner to understand.

Add short comments explaining important pieces of logic.

---

# 31. ERROR HANDLING

Every API-driven page must handle:

* loading
* successful response
* empty response
* API error
* network failure

If the API is unavailable, show something like:

# We couldn't load the movies

> Please check that the CineBook backend is running.

Then show the actual API/network error where useful.

Do not expose confusing JavaScript stack traces to users.

---

# 32. PERFORMANCE

Avoid unnecessary API calls.

Use proper React effects and cleanup.

The seat map's 10-second refresh must not create multiple intervals.

Do not reload the entire browser for seat refresh.

Only refresh the required show/seat data.

---

# 33. IMPORTANT BACKEND RULE

Do NOT modify:

`backend/`

or:

`db/`

under any circumstances.

If the backend response structure is different from what you expected, adapt the frontend to the actual backend.

The backend is the source of truth.

---

# 34. FINAL QUALITY BAR

Before considering the frontend complete, mentally review it as if you were a customer buying movie tickets.

Ask:

* Does the homepage immediately look like a real cinema product?
* Can I understand what movies are showing within seconds?
* Can I easily find showtimes?
* Is the seat map intuitive?
* Can I clearly distinguish available, selected, held, booked and premium seats?
* Is the current selection always obvious?
* Is the total price impossible to miss?
* Is the hold countdown obvious?
* Does the checkout page feel trustworthy?
* Does the mobile version feel intentionally designed?
* Are loading/error/empty states polished?
* Are there any leftover Vite starter elements?
* Are API field names exactly aligned with the backend?

The final result should feel like a **production-quality movie booking frontend**, not a tutorial/demo application.

---

# 35. IMPORTANT EXECUTION INSTRUCTION

Do not modify the backend or database.

Do not invent API endpoints or response fields.

Do not run commands.

After creating/updating the frontend files:

1. List every file you created or modified.
2. Briefly explain what each important file does.
3. Explain in simple terms how the React pages communicate with the FastAPI backend.
4. Mention the API endpoints used by the frontend.
5. Mention that no files under `backend/` or `db/` were modified.

Do NOT provide generic setup instructions unless necessary.

Focus on actually implementing the frontend in the existing `frontend/` application.
