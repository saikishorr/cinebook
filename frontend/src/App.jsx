import { BrowserRouter, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import ScrollToTop from './components/ScrollToTop'
import Movies from './pages/Movies'
import Showtimes from './pages/Showtimes'
import SeatMap from './pages/SeatMap'
import Checkout from './pages/Checkout'
import NotFound from './pages/NotFound'
import BookingConfirmation from './pages/BookingConfirmation'
import FindBooking from './pages/FindBooking'
import Cinemas from './pages/Cinemas'
import CinemaDetail from './pages/CinemaDetail'
import DemoPhone from './pages/DemoPhone'
import ChatLanding from './pages/ChatLanding'
import Help from './pages/Help'
import Admin from './pages/Admin'
import SignIn from './pages/SignIn'
import MyBookings from './pages/MyBookings'

export default function App() {
  return (
    <BrowserRouter>
      <ScrollToTop />
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Movies />} />
          <Route path="/movies/:movieId" element={<Showtimes />} />
          <Route path="/cinemas" element={<Cinemas />} />
          <Route path="/cinemas/:cinemaId" element={<CinemaDetail />} />
          <Route path="/shows/:showId" element={<SeatMap />} />
          <Route path="/checkout/:holdId" element={<Checkout />} />
          <Route path="/booking" element={<FindBooking />} />
          <Route path="/booking/:bookingRef" element={<BookingConfirmation />} />
          <Route path="/demo-phone" element={<DemoPhone />} />
          <Route path="/c/:code" element={<ChatLanding />} />
          <Route path="/help" element={<Help />} />
          <Route path="/admin/*" element={<Admin />} />
          <Route path="/login" element={<SignIn />} />
          <Route path="/register" element={<SignIn mode="register" />} />
          <Route path="/my-bookings" element={<MyBookings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
