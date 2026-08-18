import { motion, AnimatePresence } from 'framer-motion'
import { useEffect, useState } from 'react'
import { Star, X } from 'lucide-react'

const STORAGE_KEY = 'voxterm-star-prompt-seen'

export default function StarModal() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return
    const t = setTimeout(() => setOpen(true), 1200)
    return () => clearTimeout(t)
  }, [])

  const close = () => {
    setOpen(false)
    localStorage.setItem(STORAGE_KEY, '1')
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center px-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <motion.div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={close}
          />

          <motion.div
            className="relative w-full max-w-[420px] rounded-2xl border border-white/10 bg-surface p-7 shadow-2xl"
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 12 }}
            transition={{ type: 'spring', stiffness: 340, damping: 28 }}
          >
            <button
              onClick={close}
              aria-label="Close"
              className="absolute top-4 right-4 text-muted hover:text-white transition-colors"
            >
              <X size={18} />
            </button>

            <div className="flex items-center justify-center w-11 h-11 rounded-xl bg-accent/15 mb-4">
              <Star size={20} className="text-accent-mid" fill="currentColor" />
            </div>

            <h2 className="text-[18px] font-bold text-white mb-2">
              Hey, I'm a student building this solo
            </h2>

            <p className="text-[14px] leading-relaxed text-muted mb-5">
              VoxTerm is a side project I built and maintain on my own. If it's useful to you,
              a GitHub star genuinely helps — it's the main way recruiters and other developers
              find and trust student projects like this. Costs nothing, takes two seconds.
            </p>

            <div className="flex items-center gap-3">
              <motion.a
                href="https://github.com/cryptic-soorya/VoxTerm"
                target="_blank"
                onClick={close}
                className="flex items-center justify-center gap-2 flex-1 px-4 py-2.5 bg-accent text-white text-[13px] font-semibold rounded-lg"
                whileHover={{ scale: 1.02, backgroundColor: '#ff8a5c' }}
                whileTap={{ scale: 0.97 }}
              >
                <Star size={14} />
                Star on GitHub
              </motion.a>
              <button
                onClick={close}
                className="px-4 py-2.5 text-[13px] font-medium text-muted hover:text-white transition-colors"
              >
                Maybe later
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
