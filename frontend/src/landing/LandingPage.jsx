import React, { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import './LandingPage.css'

import arrowWhite from '../assets/landing/arrow-white.svg'
import ctaMascot from '../assets/landing/cta-mascot.png'
import docIcon from '../assets/landing/doc-icon.svg'
import downloadIcon from '../assets/landing/download-icon.svg'
import faqChevron from '../assets/landing/faq-chevron.svg'
import featureDocuments from '../assets/landing/feature-documents.svg'
import featureSearch from '../assets/landing/feature-search.svg'
import headerLogoMark from '../assets/landing/header-logo-mark.svg'
import heroMascot from '../assets/landing/hero-mascot.png'
import platformHackerrank from '../assets/landing/platform-hackerrank.svg'
import platformLeetcode from '../assets/landing/platform-leetcode.svg'
import platformMeet from '../assets/landing/platform-meet.svg'
import platformTeams from '../assets/landing/platform-teams.svg'
import platformZoom from '../assets/landing/platform-zoom.svg'
import playIcon from '../assets/landing/play-icon.svg'
import targetIcon from '../assets/landing/target-icon.svg'
import trustIcon from '../assets/landing/trust-icon.svg'
import videoStill from '../assets/landing/video-still.png'
import workflowMascot from '../assets/landing/workflow-mascot.png'

const navItems = [
  ['Features', '#features'],
  ['How It Works', '#how-it-works'],
  ['Product', '#product'],
  ['Pricing', '#pricing'],
  ['FAQ', '#faq'],
]

const problemCards = [
  ['Generic answers', docIcon, 'Standard AI chatbots give you the same behavioral scripts as everyone else, with no idea what you actually worked on.', 'Zero profile awareness'],
  ['Scattered prep', featureDocuments, 'Your resume, target rubrics, personal cheat sheets, and rehearsal bullet points exist in disparate browser tabs and Notion docs.', 'Constant tab toggling'],
  ['Lost takeaways', trustIcon, 'Critical technical follow-ups and exact interviewer reactions evaporate from your memory seconds after hanging up the call.', 'No post-call retention'],
  ['No role context', targetIcon, 'Blanket interview strategies miss the mark by failing to adapt to level expectations, whether L4 IC execution or Staff architectural tradeoffs.', 'Misaligned seniorities'],
]

const workflowInputs = [
  ['INPUT 01', 'Your Resume', docIcon, 'Resume indexed', 'Parse, index, and organize your experience, skills, achievements, and project history into structured interview ready context.'],
  ['INPUT 02', 'Target Role', targetIcon, 'Role mapped', 'Analyze the job description, required competencies, technical skills, and role-specific expectations.'],
  ['INPUT 03', 'Live Interview', playIcon, 'Session ready', 'Uses permitted interview context and available session information to support relevant preparation and contextual assistance.'],
]

const workflowOutputs = [
  ['OUTPUT 01', 'AI Guidance', trustIcon, 'Personalized guidance', 'Provides role-specific preparation prompts, relevant experience references, and structured guidance grounded in the candidate context.'],
  ['OUTPUT 02', 'Session Insights', featureSearch, 'Insights organized', 'Organizes interview takeaways, strengths, improvement areas, and follow-up preparation into a reusable learning history.'],
]

const featureCards = [
  ['01', 'Know what to practice before the next round.', 'Get structured practice questions, relevant technical topics, and follow-up prompts tailored to your target role and experience.', 'AI follow-ups and answer refinement', featureSearch],
  ['02', 'Turn your experience into interview-ready answers.', 'Intervu AI extracts your skills, projects, achievements, and work history to build a personal knowledge base for interview preparation.', 'Automatic parsing - PDF, DOCX, TXT', featureDocuments],
  ['03', 'Prepare for the role, not just the interview.', 'Add a job description to identify required skills, technical expectations, and role-specific competencies. Focus your preparation on what matters for the position.', 'Job requirements mapped', targetIcon],
]

const platforms = [
  ['Zoom', platformZoom],
  ['Google Meet', platformMeet],
  ['Microsoft Teams', platformTeams],
  ['HackerRank', platformHackerrank],
  ['LeetCode', platformLeetcode],
]

const trustedCompanies = ['Google', 'Microsoft', 'MongoDB', 'LinkedIn', 'PayPal', 'IBM']

const prepSlides = [
  ['03', 'Review and iterate', 'Review detailed AI debriefs, question breakdowns, and simulated follow-ups to make each round stronger than the last.', 'Continuous interview growth'],
  ['01', 'Upload your resume', 'Drop in your PDF or LinkedIn export. Intervu AI builds a structured profile from every role, metric, and project you list.', 'Automatic parsing - PDF, DOCX, TXT'],
  ['02', 'Set your job target', 'Paste the job description or enter target title and company. The engine maps key hiring rubrics and anticipated line-of-questioning.', 'Role rubric alignment calibrated'],
]

const privacyItems = [
  ['Designed with privacy-first workflows', trustIcon, 'Preparation flows are designed so users stay in control of what context is uploaded, synced, or reused.'],
  ['Backend-owned secret handling', docIcon, 'Sensitive service credentials stay on trusted backend paths, not in public website or desktop renderer code.'],
  ['User-owned records protected by RLS', targetIcon, 'Account-scoped records are designed around row-level access boundaries and explicit ownership.'],
  ['Raw screenshots/audio are not stored by default', downloadIcon, 'Live context is treated as temporary session material unless a product flow explicitly saves it.'],
]

const pricingPlans = [
  ['FREE', 'Preview', 'Explore context ingestion and standard preparation rubrics.', ['1 resume workspace', 'Practice prompts', 'Basic preparation flow'], 'Get Started'],
  ['STUDENT', 'TBD', 'Built for new grads and campus recruitment cycles.', ['Resume indexing', 'Practice arena', 'Desktop app access'], 'Join Waitlist'],
  ['PRO CANDIDATE', 'TBD', 'For active job searches across senior and staff roles.', ['Unlimited prep contexts', 'Desktop HUD support', 'Post-interview retrospectives'], 'Get Started'],
  ['INSTITUTION', 'Custom', 'For bootcamps, university career centers, and coaching teams.', ['Bulk seats', 'Coach workflows', 'Dedicated support path'], 'Contact Sales'],
]

const faqItems = [
  ['Will my interviewer know I am using the Desktop HUD?', 'The HUD runs as a lightweight overlay outside the shared window or screen in most meeting setups. Visibility still depends on your OS, meeting app, and whether you share your full screen, a single window, or a browser tab - always check your sharing scope before a live round.'],
  ['How does Intervu AI ground answers in my real work?', 'Your resume, target role, and session context are indexed into a structured profile. Every suggestion is built from that profile instead of generic scripts, so guidance reflects your actual projects, metrics, and technical decisions.'],
  ['Can I delete my transcripts and session logs?', 'Yes. Session transcripts, debriefs, and audio artifacts are tied to your account and can be removed from Workspace settings at any time. Raw screenshots and audio are not retained by default.'],
  ['Can I use Intervu AI for mock practice before real rounds?', 'Yes. The Practice Arena lets you rehearse against your indexed resume and target role before a live interview, so you can validate answers and timing ahead of the real conversation.'],
]

function BrandMark({ footer = false }) {
  return (
    <a className="landing-brand" href="#top" aria-label="Intervu AI home">
      <span className="landing-brand__icon">
        <img src={headerLogoMark} alt="" />
      </span>
      <span className={footer ? 'landing-brand__copy landing-brand__copy--footer' : 'landing-brand__copy'}>
        Intervu AI
      </span>
    </a>
  )
}

function Header() {
  return (
    <header className="landing-header" id="top">
      <nav className="landing-nav" aria-label="Primary">
        <BrandMark />
        <div className="landing-nav__links">
          {navItems.map(([label, href]) => <a key={label} href={href}>{label}</a>)}
        </div>
        <div className="landing-nav__actions">
          <a className="landing-login" href="/auth/login">Log in</a>
          <a className="landing-button landing-button--small" href="/auth/signup">Get Started <img src={arrowWhite} alt="" /></a>
        </div>
      </nav>
    </header>
  )
}

const heroEase = [0.22, 1, 0.36, 1]

const heroCopyGroup = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
}

const heroCopyItem = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.55, ease: heroEase } },
}

const heroVisualReveal = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.7, ease: heroEase, delay: 0.2 } },
}

const equationGroup = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.14, delayChildren: 1.1 } },
}

const equationTerm = {
  hidden: { opacity: 0, y: 8, scale: 0.9 },
  visible: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.32, ease: heroEase } },
}

const equationResult = {
  hidden: { opacity: 0, scale: 0.7 },
  visible: {
    opacity: 1,
    scale: [0.7, 1.12, 1],
    transition: { duration: 0.45, ease: heroEase },
  },
}

function floatLoop(duration, delay = 0) {
  return {
    y: [0, -8, 0],
    transition: { duration, delay, repeat: Infinity, ease: 'easeInOut' },
  }
}

function FloatingCard({ className, entryDelay, floatDuration, reduceMotion, children }) {
  const [hasEntered, setHasEntered] = useState(false)

  if (reduceMotion) {
    return <div className={className}>{children}</div>
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 28, scale: 0.96 }}
      animate={hasEntered ? { ...floatLoop(floatDuration), opacity: 1, scale: 1 } : { opacity: 1, y: 0, scale: 1 }}
      transition={hasEntered ? undefined : { duration: 0.6, delay: entryDelay, ease: heroEase }}
      onAnimationComplete={() => setHasEntered(true)}
    >
      {children}
    </motion.div>
  )
}

function Hero() {
  const reduceMotion = useReducedMotion()

  return (
    <section className="landing-hero">
      <motion.div
        className="landing-hero__copy"
        initial={reduceMotion ? false : 'hidden'}
        animate="visible"
        variants={heroCopyGroup}
      >
        <motion.p className="landing-pill" variants={heroCopyItem}><span /> SMART AI INTERVIEW ASSISTANT - CONTEXT-AWARE INTELLIGENCE</motion.p>
        <motion.h1 variants={heroCopyItem}>Walk into every <span>interview prepared.</span></motion.h1>
        <motion.p className="landing-lede" variants={heroCopyItem}>
          AI that understands your resume, your target role, and your interview context - helping you prepare smarter, respond with precision, and learn from every conversation.
        </motion.p>
        <motion.div className="landing-actions" variants={heroCopyItem}>
          <a className="landing-button" href="/auth/signup">Get Started <img src={arrowWhite} alt="" /></a>
          <a className="landing-button landing-button--secondary" href="#how-it-works"><img src={playIcon} alt="" /> See How It Works</a>
        </motion.div>
        <motion.p className="landing-trust" variants={heroCopyItem}><img src={trustIcon} alt="" /> Resume-powered / Job-targeted / AI-assisted. Built around your actual context.</motion.p>
      </motion.div>
      <motion.div
        className="landing-hero__visual"
        aria-label="Intervu AI interview preparation preview"
        initial={reduceMotion ? false : 'hidden'}
        animate="visible"
        variants={heroVisualReveal}
      >
        <motion.div
          className="landing-glow"
          animate={reduceMotion ? undefined : { opacity: [0.85, 1, 0.85] }}
          transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
        />
        <FloatingCard className="floating-card floating-card--top" entryDelay={0.55} floatDuration={6.5} reduceMotion={reduceMotion}>
          <strong className="floating-card__live-label">
            {reduceMotion ? (
              <span className="floating-card__live-dot" />
            ) : (
              <motion.span
                className="floating-card__live-dot"
                animate={{ opacity: [1, 0.35, 1], scale: [1, 0.85, 1] }}
                transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
              />
            )}
            AI LIVE GUIDANCE
          </strong>
          <p>"Highlight your distributed systems experience in Go and latency optimizations when discussing this role."</p>
        </FloatingCard>
        <img className="landing-hero__mascot" src={heroMascot} alt="Intervu AI mascot" />
        <FloatingCard className="floating-card floating-card--left" entryDelay={0.7} floatDuration={7.5} reduceMotion={reduceMotion}>
          <img src={docIcon} alt="" />
          <div><strong>RESUME SOURCE</strong><p>4.2 MB PDF Indexed</p><small>Senior Software Eng</small></div>
        </FloatingCard>
        <FloatingCard className="floating-card floating-card--right" entryDelay={0.85} floatDuration={7} reduceMotion={reduceMotion}>
          <img src={targetIcon} alt="" />
          <div><strong>TARGET CONTEXT</strong><p>Staff Backend @ Nimbus Cloud</p><small>System Design / Concurrency</small></div>
        </FloatingCard>
        <motion.div
          className="equation-bar"
          initial={reduceMotion ? false : 'hidden'}
          animate="visible"
          variants={equationGroup}
        >
          <motion.span variants={equationTerm}>RESUME</motion.span>
          <motion.b variants={equationTerm}>+</motion.b>
          <motion.span variants={equationTerm}>TARGET ROLE</motion.span>
          <motion.b variants={equationTerm}>+</motion.b>
          <motion.span variants={equationTerm}>LIVE CONTEXT</motion.span>
          <motion.b variants={equationTerm}>=</motion.b>
          <motion.span className="equation-bar__result" variants={equationResult}>Intervu AI</motion.span>
        </motion.div>
      </motion.div>
    </section>
  )
}

function ProblemSection() {
  return (
    <section className="landing-section" id="problem">
      <div className="section-heading">
        <p>THE PREPARATION GAP</p>
        <h2>Interviews shouldn't feel like guesswork.</h2>
        <span>Interview preparation is often fragmented. Your resume, job description, preparation notes, and interview conversations live in completely disconnected places.</span>
      </div>
      <div className="video-card">
        <img src={videoStill} alt="Candidate preparing for a remote interview" />
        <div className="video-card__overlay">
          <h3>Your next interview starts before you enter the room.</h3>
          <a className="landing-button" href="#how-it-works">Play Video <img src={arrowWhite} alt="" /></a>
        </div>
      </div>
      <div className="problem-grid">
        {problemCards.map(([title, icon, body, note]) => (
          <article className="problem-card" key={title}>
            <div className="problem-card__icon"><img src={icon} alt="" /></div>
            <h3>{title}</h3>
            <p>{body}</p>
            <small>{note}</small>
          </article>
        ))}
      </div>
    </section>
  )
}

function WorkflowSection() {
  return (
    <section className="landing-section" id="how-it-works">
      <div className="section-heading">
        <h2>Your entire interview journey. One intelligent AI.</h2>
        <span>From resume analysis to personalized interview guidance, Intervu AI connects every step to help you prepare with confidence.</span>
      </div>
      <div className="architecture-panel">
        <div className="architecture-column">
          <div className="architecture-label"><span>CANDIDATE INPUTS</span><b>3 Streams</b></div>
          {workflowInputs.map(([kicker, title, icon, status, body], index) => (
            <article className={index === 0 ? 'architecture-node architecture-node--active' : 'architecture-node'} key={title}>
              <div><img src={icon} alt="" /><span><b>{kicker}</b><strong>{title}</strong></span></div>
              <em>{status}</em>
              <p>{body}</p>
            </article>
          ))}
        </div>
        <div className="architecture-core" id="product">
          <img src={workflowMascot} alt="Intervu AI core engine mascot" />
          <span>CORE ENGINE</span>
          <h3>Intervu AI</h3>
          <p>Connects your experience, target role, and interview context to generate relevant, personalized preparation intelligence.</p>
          <small>Context synchronized</small>
        </div>
        <div className="architecture-column">
          <div className="architecture-label"><span>INTELLIGENT OUTPUTS</span><b>Real-Time Results</b></div>
          {workflowOutputs.map(([kicker, title, icon, status, body]) => (
            <article className="architecture-node" key={title}>
              <div><img src={icon} alt="" /><span><b>{kicker}</b><strong>{title}</strong></span></div>
              <em>{status}</em>
              <p>{body}</p>
            </article>
          ))}
        </div>
        <div className="architecture-detail">
          <strong>INPUT 01 - RESUME CONTEXT</strong>
          <small>Interactive Deep-Dive</small>
          <h3>Your experience becomes structured context.</h3>
          <p>Intervu AI organizes skills, projects, achievements, and work history into information that can support more relevant preparation.</p>
          <span>Click any node to explore</span>
        </div>
      </div>
    </section>
  )
}

const featureTabLabels = ['Resume', 'Job Match', 'Live Assist']

function FeatureSection() {
  const [activeIndex, setActiveIndex] = useState(1)

  return (
    <section className="landing-section feature-section" id="features">
      <div className="section-heading">
        <p>BESPOKE PREPARATION</p>
        <h2>Everything you need to prepare smarter.</h2>
        <span>From deep resume ingestion to post-interview reflection, Intervu AI keeps your preparation completely coherent.</span>
      </div>
      <div className="feature-tabbar" aria-label="Feature highlights">
        {featureTabLabels.map((label, index) => (
          <button
            type="button"
            className={index === activeIndex ? 'is-active' : ''}
            key={label}
            onClick={() => setActiveIndex(index)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="feature-slider">
        {featureCards.map(([number, title, body, note, image], index) => (
          <article className={index === activeIndex ? 'feature-slide feature-slide--active' : 'feature-slide'} key={title}>
            <img src={image} alt="" />
            <span>{number}</span>
            <h3>{title}</h3>
            <p>{body}</p>
            <small>{note}</small>
          </article>
        ))}
      </div>
    </section>
  )
}

function PlatformSection() {
  return (
    <section className="landing-section platform-section">
      <div className="section-heading">
        <p className="section-badge">WORKS EVERYWHERE</p>
        <h2>Works on every interview platform.</h2>
        <span>Zoom, Google Meet, Microsoft Teams, HackerRank, LeetCode - Intervu AI works alongside the platforms candidates already use.</span>
      </div>
      <div className="platform-rail">
        {platforms.map(([name, logo]) => (
          <div className="platform-logo" key={name}>
            <img src={logo} alt="" />
            <strong>{name}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}

function TrustedSection() {
  return (
    <section className="trusted-section">
      <div>
        <p>TRUSTED BY CANDIDATES AT</p>
        <h2>Used for 1,000,000+ interviews</h2>
      </div>
      <div className="trusted-rail" aria-label="Company logo marquee">
        {[...trustedCompanies, ...trustedCompanies].map((company, index) => (
          <span key={`${company}-${index}`}>{company}</span>
        ))}
      </div>
    </section>
  )
}

function ProductShowcase() {
  return (
    <section className="landing-section workspace-section">
      <div className="section-heading">
        <p>UNIFIED WORKSPACE</p>
        <h2>One workspace for your entire interview journey.</h2>
        <span>Track candidate metrics, review indexed resumes, explore target company rubrics, and inspect simulated question banks.</span>
      </div>
      <div className="dashboard-window" aria-label="Intervu AI dashboard preview">
        <div className="browser-bar">
          <span /><span /><span />
          <strong>app.intervu.ai/workspace/sessions/nimbus-staff-round</strong>
        </div>
        <div className="dashboard-grid">
          <aside>
            <div className="profile-chip"><b>JD</b><span>Jane Doe<br />Senior Backend Candidate</span></div>
            {['Active Workspace', 'Resume Knowledge', 'Target Rubrics', 'Practice Arena'].map((item) => <a key={item}>{item}</a>)}
          </aside>
          <main>
            <div className="metric-grid">
              <article><small>READINESS SCORE</small><b>92%</b><p>Resume & Desktop sync verified</p></article>
              <article><small>ACTIVE TARGET</small><b>Nimbus Cloud</b><p>Staff Infrastructure / Band L6</p></article>
              <article><small>INDEXED SOURCES</small><b>3 Documents</b><p>Resume / GitHub repo / Patents</p></article>
              <article><small>HUD SESSION</small><b>Standby</b><p>Audio daemon connected</p></article>
            </div>
            <section className="intelligence-panel">
              <h3>LATEST SESSION INTELLIGENCE</h3>
              <p>System Architecture Round / 38 min</p>
              <div><b>14 Questions Analyzed</b><b>3 Strengths Mapped</b></div>
              <article><strong>Technical Specificity</strong><span>96%</span><p>Strong quantification of cache eviction latency and consensus protocol trade-offs.</p></article>
              <article><strong>Role Rubric Alignment</strong><span>88%</span><p>Could further emphasize cross-functional stakeholder management in final system choices.</p></article>
            </section>
          </main>
        </div>
      </div>
    </section>
  )
}

function PreparationWorkflow() {
  const [activeIndex, setActiveIndex] = useState(1)
  const stepCount = prepSlides.length

  function showPrevious() {
    setActiveIndex((current) => (current - 1 + stepCount) % stepCount)
  }

  function showNext() {
    setActiveIndex((current) => (current + 1) % stepCount)
  }

  return (
    <section className="landing-section prep-section">
      <div className="section-heading">
        <p>SEAMLESS PREPARATION WORKFLOW</p>
        <h2>From preparation to reflection, in one flow.</h2>
        <span>A structured, repeatable protocol designed to build confidence in high-stakes technical and leadership interviews.</span>
      </div>
      <div className="prep-slider">
        <button type="button" aria-label="Previous preparation step" onClick={showPrevious}>{'<'}</button>
        {prepSlides.map(([number, title, body, note], index) => (
          <article className={index === activeIndex ? 'prep-card prep-card--active' : 'prep-card'} key={title}>
            <span>{number}</span>
            <h3>{title}</h3>
            <p>{body}</p>
            <small>{note}</small>
          </article>
        ))}
        <button type="button" aria-label="Next preparation step" onClick={showNext}>{'>'}</button>
      </div>
    </section>
  )
}

function DesktopSection() {
  return (
    <section className="landing-section desktop-section" id="desktop">
      <div className="desktop-card">
        <div>
          <p>DESKTOP HUD COMPANION</p>
          <h2>Bring Intervu AI directly into your interview workflow.</h2>
          <span>A cohesive duo: the Web Workspace handles deep resume curation, role target rubrics, and longitudinal analytics. The Desktop App remains docked during live interviews for real-time memory cues.</span>
          <div className="landing-actions">
            <a className="landing-button" href="#desktop">Download Desktop App <img src={downloadIcon} alt="" /></a>
            <a className="landing-button landing-button--secondary" href="#how-it-works">Learn How It Works</a>
          </div>
          <ul>
            <li>Screen-share aware workflow</li>
            <li>Low CPU footprint</li>
            <li>Universal meeting support</li>
          </ul>
        </div>
        <div className="hud-mock">
          <strong>Intervu AI HUD - ACTIVE</strong>
          <small>MINIMAL MODE</small>
          <h3>INTERVIEWER QUESTION</h3>
          <p>"Why choose Cassandra over Postgres for this event stream?"</p>
          <h3>YOUR CONTEXT BULLETS</h3>
          <p>Handled 80k/sec write-heavy ingestion<br />Tunable consistency matched loss tolerance<br />Postgres vacuum contention became bottleneck</p>
        </div>
      </div>
    </section>
  )
}

function PrivacySection() {
  return (
    <section className="landing-section privacy-section">
      <div className="section-heading">
        <p>ENTERPRISE GRADE INTEGRITY</p>
        <h2>Your data. Your control.</h2>
        <span>We treat your career history, preparation notes, and session data as private preparation context.</span>
      </div>
      <div className="privacy-grid">
        {privacyItems.map(([title, icon, body]) => (
          <article className="privacy-card" key={title}>
            <img src={icon} alt="" />
            <h3>{title}</h3>
            <p>{body}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

function PricingSection() {
  const [isYearly, setIsYearly] = useState(true)

  return (
    <section className="pricing-section" id="pricing">
      <div className="section-heading">
        <p>TRANSPARENT INVESTMENT</p>
        <h2>Choose the plan that fits your preparation.</h2>
        <span>Plan packaging is shown as a preview while public pricing is finalized.</span>
      </div>
      <div className="billing-toggle" role="group" aria-label="Billing period preview">
        <button type="button" className={isYearly ? '' : 'is-active'} onClick={() => setIsYearly(false)}>Monthly</button>
        <button type="button" className={isYearly ? 'is-active' : ''} onClick={() => setIsYearly(true)}>Yearly</button>
        <b>SAVE 20%</b>
      </div>
      <div className="pricing-grid">
        {pricingPlans.map(([name, price, body, features, action], index) => (
          <article className={index === 2 ? 'price-card price-card--featured' : 'price-card'} key={name}>
            {index === 2 ? <span className="recommended">RECOMMENDED</span> : null}
            <h3>{name}</h3>
            <strong>{price}</strong>
            <p>{body}</p>
            <ul>{features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
            <a className={index === 2 ? 'landing-button' : 'landing-button landing-button--secondary'} href={index === 3 ? '#footer' : '/auth/signup'}>{action}</a>
          </article>
        ))}
      </div>
    </section>
  )
}

function FAQSection() {
  const [openIndex, setOpenIndex] = useState(null)

  function toggle(index) {
    setOpenIndex((current) => (current === index ? null : index))
  }

  return (
    <section className="landing-section faq-section" id="faq">
      <div className="section-heading">
        <p>CLEAR CLARITY</p>
        <h2>Questions, answered.</h2>
        <span>Everything you need to know about how Intervu AI operates during your job search.</span>
      </div>
      <div className="faq-list">
        {faqItems.map(([question, answer], index) => {
          const isOpen = openIndex === index
          return (
            <div className={isOpen ? 'faq-item faq-item--open' : 'faq-item'} key={question}>
              <div
                className="faq-row"
                role="button"
                tabIndex={0}
                aria-expanded={isOpen}
                onClick={() => toggle(index)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    toggle(index)
                  }
                }}
              >
                <span>{question}</span>
                <img src={faqChevron} alt="" className={isOpen ? 'faq-chevron faq-chevron--open' : 'faq-chevron'} />
              </div>
              {isOpen ? <p className="faq-answer">{answer}</p> : null}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function CTASection() {
  return (
    <section className="landing-section cta-section">
      <div className="cta-card">
        <div className="cta-lines cta-lines--left" />
        <div className="cta-lines cta-lines--right" />
        <img src={ctaMascot} alt="Intervu AI mascot" />
        <h2>Your next interview starts before you enter the room.</h2>
        <p>Join ambitious engineers and professionals turning interview anxiety into structured, context-rich confidence.</p>
        <div className="landing-actions">
          <a className="landing-button" href="/auth/signup">Get Started <img src={arrowWhite} alt="" /></a>
          <a className="landing-button landing-button--secondary" href="#desktop"><img src={downloadIcon} alt="" /> Download Desktop App</a>
        </div>
        <small>No credit card required / macOS and Windows compatible / Ready in 2 minutes</small>
      </div>
    </section>
  )
}

function Footer() {
  const columns = [
    ['PRODUCT', ['Features', 'Workflow Engine', 'Telemetry Cockpit', 'Pricing Tiers']],
    ['RESOURCES', ['Documentation', 'FAQ', 'Security & Compliance', 'API References']],
    ['ACCOUNT & LEGAL', ['Log in', 'Create Account', 'Privacy Policy', 'Terms of Service']],
  ]

  return (
    <footer className="landing-footer" id="footer">
      <div className="landing-footer__brand">
        <BrandMark footer />
        <strong>SMART AI INTERVIEW ASSISTANT</strong>
        <p>Helping candidates prepare with structured context, role-aware workflows, and user-controlled interview practice.</p>
      </div>
      {columns.map(([heading, links]) => (
        <nav key={heading} aria-label={heading}>
          <h3>{heading}</h3>
          {links.map((link) => <a key={link} href={link === 'Log in' ? '/auth/login' : '#top'}>{link}</a>)}
        </nav>
      ))}
      <div className="landing-footer__bottom">
        <span>(c) 2025 Intervu AI Systems Inc. All rights reserved.</span>
        <span><a href="#top">Privacy</a><a href="#top">Terms</a><a href="#top">Security</a></span>
      </div>
    </footer>
  )
}

function useScrollReveal() {
  useEffect(() => {
    const targets = document.querySelectorAll(
      '.landing-page .landing-section, .landing-page .trusted-section, .landing-page .pricing-section'
    )

    if (!targets.length) {
      return undefined
    }

    if (typeof IntersectionObserver === 'undefined') {
      targets.forEach((el) => el.classList.add('is-visible'))
      return undefined
    }

    targets.forEach((el) => el.classList.add('reveal-on-scroll'))

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.12, rootMargin: '0px 0px -60px 0px' }
    )

    targets.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])
}

export default function LandingPage() {
  useScrollReveal()

  return (
    <div className="landing-page">
      <Header />
      <main>
        <Hero />
        <ProblemSection />
        <WorkflowSection />
        <FeatureSection />
        <PlatformSection />
        <TrustedSection />
        <ProductShowcase />
        <PreparationWorkflow />
        <DesktopSection />
        <PrivacySection />
        <PricingSection />
        <FAQSection />
        <CTASection />
      </main>
      <Footer />
    </div>
  )
}
