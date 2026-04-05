import Nav from './components/Nav'
import Hero from './components/Hero'
import Problem from './components/Problem'
import HowItWorks from './components/HowItWorks'
import Features from './components/Features'
import Privacy from './components/Privacy'
import Safety from './components/Safety'
import Download from './components/Download'
import Footer from './components/Footer'

export default function App() {
  return (
    <div className="min-h-screen bg-bg text-white">
      <Nav />
      <Hero />
      <Problem />
      <HowItWorks />
      <Features />
      <Privacy />
      <Safety />
      <Download />
      <Footer />
    </div>
  )
}
