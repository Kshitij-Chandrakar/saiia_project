import { useEffect, useId, useRef, useState } from 'react'
import walkingAtlas from '../assets/website-signup/robot-walk-atlas.png'
import doorwayAtlas from '../assets/website-signup/door-atlas.png'
import fallback from '../assets/website-signup/mascot.png'
import './signup-mascot.css'

const gait = [1, 2, 3, 4, 5, 6]
const ease = value => value * value * (3 - 2 * value)

// One finite timeline; travel and the genuine character poses are separate layers.
export function signupMascotPose(elapsed) {
  const walk = Math.max(0, Math.min(1, (elapsed - 1550) / 1800))
  const opening = Math.max(0, Math.min(1, (elapsed - 1000) / 650))
  return {
    phase: elapsed < 1000 ? 'waiting' : elapsed < 1550 ? 'opening' : elapsed < 3350 ? 'walking' : elapsed < 3650 ? 'settling' : elapsed < 4000 ? 'greeting' : 'complete',
    angle: -108 * ease(opening),
    progress: ease(walk),
    frame: elapsed >= 3350 ? 7 : elapsed < 1550 ? 0 : gait[Math.min(11, Math.floor((elapsed - 1550) / 150)) % gait.length],
    greeting: ease(Math.max(0, Math.min(1, (elapsed - 3650) / 350))),
  }
}

export default function SignupMascot() {
  const scene = useRef(null)
  const [failed, setFailed] = useState(false)
  const id = useId().replace(/:/g, '')
  useEffect(() => {
    let active = true
    let frame = 0
    let loaded = false
    const entered = performance.now()
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const root = scene.current
    const door = root.querySelector('[data-door]')
    const robot = root.querySelector('[data-robot]')
    const sprite = root.querySelector('[data-sprite]')
    const bubble = root.querySelector('[data-bubble]')
    const shadow = root.querySelector('[data-shadow]')
    const aperture = root.querySelector('[data-aperture]')
    function draw(elapsed) {
      const pose = signupMascotPose(elapsed)
      root.dataset.phase = pose.phase
      root.dataset.frame = String(pose.frame)
      root.dataset.elapsed = String(Math.round(elapsed))
      door.style.transform = `rotateY(${pose.angle}deg)`
      const scale = .515 + pose.progress * .055
      const x = 241 - pose.progress * 103
      const gaitBob = elapsed >= 1550 && elapsed < 3350 ? -1.5 * Math.sin(((elapsed - 1550) % 450) / 450 * Math.PI) : elapsed >= 3350 && elapsed < 3650 ? 1.5 * Math.sin((elapsed - 3350) / 300 * Math.PI) : 0
      const y = 100 + pose.progress * 33 + gaitBob
      robot.setAttribute('opacity', elapsed <= 1000 ? '0' : '1')
      const clearance = ease(Math.max(0, Math.min(1, (elapsed - 1550) / 650)))
      aperture.setAttribute('x', String(263 * (1 - clearance)))
      aperture.setAttribute('width', String(159 + 321 * clearance))
      robot.setAttribute('transform', `translate(${x} ${y}) scale(${scale})`)
      sprite.setAttribute('viewBox', `${(pose.frame % 4) * 384} ${Math.floor(pose.frame / 4) * 512} 384 512`)
      bubble.setAttribute('opacity', String(pose.greeting))
      bubble.setAttribute('transform', `translate(38 ${42 + 4 * (1 - pose.greeting)})`)
      shadow.setAttribute('cx', String(x + 192 * scale))
      shadow.setAttribute('cy', String(y + 497 * scale))
      shadow.setAttribute('rx', String(72 * scale))
      root.dataset.ready = 'true'
    }
    function motionPreference() {
      cancelAnimationFrame(frame)
      if (loaded) draw(4000) // Switching preferences never replays an entrance.
    }
    const images = [walkingAtlas, doorwayAtlas].map(src => {
      const image = new Image()
      return new Promise((resolve, reject) => {
        image.onload = resolve
        image.onerror = reject
        image.src = src
      })
    })
    Promise.all(images).then(() => {
      if (!active) return
      loaded = true
      root.dataset.assetsLoaded = 'true'
      const ready = performance.now()
      const openingAt = Math.max(entered + 1000, ready)
      function tick(now) {
        if (!active) return
        const elapsed = media.matches ? 4000 : now < openingAt ? 0 : 1000 + now - openingAt
        draw(elapsed)
        if (elapsed < 4000) frame = requestAnimationFrame(tick)
      }
      frame = requestAnimationFrame(tick)
    }).catch(() => { if (active) setFailed(true) })
    media.addEventListener('change', motionPreference)
    return () => {
      active = false
      cancelAnimationFrame(frame)
      media.removeEventListener('change', motionPreference)
    }
  }, [])

  return <svg ref={scene} className="website-signup__mascot signup-mascot-scene" viewBox="0 0 480 420" role="img" aria-label="Friendly Intervucopilot robot opening a door, walking out and saying Welcome" data-phase={failed ? 'fallback' : 'waiting'}>
    <defs>
      <radialGradient id={`${id}-shadow`}><stop stopColor="#173b79" stopOpacity=".25" /><stop offset="1" stopColor="#173b79" stopOpacity="0" /></radialGradient>
      <clipPath id={`${id}-aperture`} clipPathUnits="userSpaceOnUse"><rect data-aperture x="263" y="0" width="159" height="420" /></clipPath>
      <clipPath id={`${id}-fallback`}><path d="M480 0H1350V1165H0V450H480Z" /></clipPath>
    </defs>
    {failed ? <svg x="18" y="0" width="444" height="400" viewBox="0 0 1350 1165"><image href={fallback} width="1350" height="1165" clipPath={`url(#${id}-fallback)`} /></svg> : <>
      <svg x="180" y="0" width="277" height="420" viewBox="0 0 675 1024"><image href={doorwayAtlas} width="1536" height="1024" /></svg>
      <ellipse data-shadow cx="340" cy="356" rx="40" ry="12" fill={`url(#${id}-shadow)`} />
      <g clipPath={`url(#${id}-aperture)`}><g data-robot opacity="0" transform="translate(241 100) scale(.515)">
        <svg data-sprite width="384" height="512" viewBox="0 0 384 512"><image href={walkingAtlas} width="1536" height="1024" /></svg>
      </g></g>
      <foreignObject x="255" y="45" width="165" height="324" className="signup-mascot-door-space">
        <div className="signup-mascot-door" data-door><svg viewBox="675 50 430 930" width="100%" height="100%" aria-hidden="true"><image href={doorwayAtlas} width="1536" height="1024" /></svg></div>
      </foreignObject>
    </>}
    <g data-bubble transform="translate(38 42)" opacity={failed ? 1 : 0} aria-hidden="true">
      <path d="M42 77Q42 65 54 65H163Q175 65 175 77V106Q175 118 163 118H145L150 135L125 118H54Q42 118 42 106Z" fill="#f8fafc" stroke="#82d9fb" strokeWidth="2" />
      <text x="108" y="100" textAnchor="middle" fill="#0058bf" fontFamily="Website Inter, sans-serif" fontWeight="700" fontSize="22">Welcome</text>
    </g>
  </svg>
}
