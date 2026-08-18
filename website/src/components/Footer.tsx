import { motion } from 'framer-motion'
import { Github } from 'lucide-react'

const LINKS = [
  { label: 'GitHub',    href: 'https://github.com/cryptic-soorya/VoxTerm' },
  { label: 'Releases',  href: 'https://github.com/cryptic-soorya/VoxTerm/releases' },
  { label: 'Issues',    href: 'https://github.com/cryptic-soorya/VoxTerm/issues' },
  { label: 'MIT Licence', href: 'https://github.com/cryptic-soorya/VoxTerm/blob/main/LICENSE' },
]

export default function Footer() {
  return (
    <footer className="border-t border-white/[0.05] py-10 px-8">
      <div className="max-w-[1040px] mx-auto flex flex-wrap items-center justify-between gap-4">
        <motion.div
          className="text-[14px] font-bold"
          whileHover={{ opacity: 0.7 }}
        >
          Vox<span className="text-accent-mid">Term</span>
          <span className="text-muted font-normal ml-2">by soorya</span>
        </motion.div>

        <div className="flex items-center gap-6 flex-wrap">
          {LINKS.map(l => (
            <motion.a
              key={l.label}
              href={l.href}
              target="_blank"
              className="text-[13px] text-muted"
              whileHover={{ color: '#f0f0f8' }}
              transition={{ duration: 0.15 }}
            >
              {l.label}
            </motion.a>
          ))}
        </div>

        <div className="text-[12px] text-muted2">Free. Open source. No tracking.</div>
      </div>
    </footer>
  )
}
