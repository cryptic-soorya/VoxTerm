import { motion, useScroll, useMotionValueEvent } from 'framer-motion'
import { useState } from 'react'
import { Github, Download } from 'lucide-react'

export default function Nav() {
  const [scrolled, setScrolled] = useState(false)
  const { scrollY } = useScroll()

  useMotionValueEvent(scrollY, 'change', (v) => setScrolled(v > 24))

  return (
    <motion.nav
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 h-14"
      animate={{
        backgroundColor: scrolled ? 'rgba(7,7,15,0.8)' : 'rgba(7,7,15,0)',
        borderBottomColor: scrolled ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0)',
        backdropFilter: scrolled ? 'blur(20px)' : 'blur(0px)',
      }}
      style={{ borderBottom: '1px solid transparent' }}
      transition={{ duration: 0.3 }}
    >
      <motion.a
        href="#"
        className="text-[15px] font-bold tracking-tight"
        whileHover={{ opacity: 0.8 }}
      >
        Vox<span className="text-accent-mid">Term</span>
      </motion.a>

      <div className="flex items-center gap-6">
        {['How it works', 'Privacy', 'Safety'].map((label) => (
          <motion.a
            key={label}
            href={`#${label.toLowerCase().replace(/ /g, '-')}`}
            className="text-[13px] font-medium text-muted hidden md:block"
            whileHover={{ color: '#f0f0f8' }}
            transition={{ duration: 0.15 }}
          >
            {label}
          </motion.a>
        ))}

        <motion.a
          href="https://github.com/yourusername/vocterm"
          target="_blank"
          className="text-muted hidden md:flex items-center"
          whileHover={{ color: '#f0f0f8', scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
        >
          <Github size={17} />
        </motion.a>

        <motion.a
          href="#download"
          className="flex items-center gap-2 px-4 py-2 bg-accent text-white text-[13px] font-semibold rounded-lg"
          whileHover={{ scale: 1.03, backgroundColor: '#9d5cff' }}
          whileTap={{ scale: 0.97 }}
          transition={{ type: 'spring', stiffness: 400, damping: 25 }}
        >
          <Download size={13} />
          Download
        </motion.a>
      </div>
    </motion.nav>
  )
}
