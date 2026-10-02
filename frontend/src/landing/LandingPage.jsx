import React, { useEffect, useRef, useState } from 'react'
import './LandingPage.css'
import heroImgSaiiaAiMascot from '../assets/landing/figma-hero-saiia-ai-mascot.png'
import heroImgContainer from '../assets/landing/figma-hero-container.svg'
import heroImgContainer1 from '../assets/landing/figma-hero-container1.svg'
import heroImgContainer2 from '../assets/landing/figma-hero-container2.svg'
import heroImgContainer3 from '../assets/landing/figma-hero-container3.svg'
import heroImgContainer4 from '../assets/landing/figma-hero-container4.svg'
import problemImgContainer from '../assets/landing/figma-problem-container.svg'
import problemImgContainer1 from '../assets/landing/figma-problem-container1.svg'
import problemImgContainer2 from '../assets/landing/figma-problem-container2.svg'
import problemImgContainer3 from '../assets/landing/figma-problem-container3.svg'
import problemImgContainer4 from '../assets/landing/figma-problem-container4.svg'
import problemImgContainer5 from '../assets/landing/figma-problem-container5.svg'
import workflowImgSaiiaCoreEngine from '../assets/landing/figma-workflow-saiia-core-engine.png'
import workflowImgContainer from '../assets/landing/figma-workflow-container.svg'
import workflowImgContainer1 from '../assets/landing/figma-workflow-container1.svg'
import workflowImgContainer2 from '../assets/landing/figma-workflow-container2.svg'
import workflowImgContainer3 from '../assets/landing/figma-workflow-container3.svg'
import workflowImgContainer4 from '../assets/landing/figma-workflow-container4.svg'
import workflowImgContainer5 from '../assets/landing/figma-workflow-container5.svg'
import workflowImgContainer6 from '../assets/landing/figma-workflow-container6.svg'
import featuresImgContainer from '../assets/landing/figma-feature-container.svg'
import featuresImgBackgroundComplete from '../assets/landing/figma-feature-background-complete.svg'
import featuresImgBackgroundSimple from '../assets/landing/figma-feature-background-simple.svg'
import featuresImgShadow from '../assets/landing/figma-feature-shadow.svg'
import featuresImgFloor from '../assets/landing/figma-feature-floor.svg'
import featuresImgDevice from '../assets/landing/figma-feature-device.svg'
import featuresImgFiles from '../assets/landing/figma-feature-files.svg'
import featuresImgCharacter from '../assets/landing/figma-feature-character.svg'
import featuresImgPlant from '../assets/landing/figma-feature-plant.svg'
import featuresImgContainer1 from '../assets/landing/figma-feature-container1.svg'
import featuresImgFloor1 from '../assets/landing/figma-feature-floor1.svg'
import featuresImgFilingCabinets from '../assets/landing/figma-feature-filing-cabinets.svg'
import featuresImgPlants from '../assets/landing/figma-feature-plants.svg'
import featuresImgFolder2 from '../assets/landing/figma-feature-folder2.svg'
import featuresImgFolder1 from '../assets/landing/figma-feature-folder1.svg'
import featuresImgDocuments from '../assets/landing/figma-feature-documents.svg'
import featuresImgContainer2 from '../assets/landing/figma-feature-container2.svg'
import featuresImgFloor2 from '../assets/landing/figma-feature-floor2.svg'
import featuresImgShadow1 from '../assets/landing/figma-feature-shadow1.svg'
import featuresImgPlants1 from '../assets/landing/figma-feature-plants1.svg'
import featuresImgGear from '../assets/landing/figma-feature-gear.svg'
import featuresImgDevice1 from '../assets/landing/figma-feature-device1.svg'
import featuresImgCharacter1 from '../assets/landing/figma-feature-character1.svg'
import featuresImgCloud from '../assets/landing/figma-feature-cloud.svg'
import platformsImgCibHackerrank from '../assets/landing/figma-platform-cib-hackerrank.svg'
import platformsImgLogosMicrosoftTeams from '../assets/landing/figma-platform-logos-microsoft-teams.svg'
import platformsImgSelfhstGoogleMeet from '../assets/landing/figma-platform-selfhst-google-meet.svg'
import platformsImgFa7BrandsZoom from '../assets/landing/figma-platform-fa7-brands-zoom.svg'
import platformsImgGroup from '../assets/landing/figma-platform-group.svg'
import platformsImgGroup1 from '../assets/landing/figma-platform-group1.svg'
import platformsImgThesvgColorLeetcode from '../assets/landing/figma-platform-thesvg-color-leetcode.svg'
import trustedImgDeviconFacebook from '../assets/landing/figma-trusted-devicon-facebook.svg'
import trustedImgBxlTwitter from '../assets/landing/figma-trusted-bxl-twitter.svg'
import trustedImgDeviconLinkedin from '../assets/landing/figma-trusted-devicon-linkedin.svg'
import trustedImgLogosNetflix from '../assets/landing/figma-trusted-logos-netflix.svg'
import trustedImgLogosMeta from '../assets/landing/figma-trusted-logos-meta.svg'
import trustedImgSkillIconsMongodb from '../assets/landing/figma-trusted-skill-icons-mongodb.svg'
import trustedImgSvg from '../assets/landing/figma-trusted-svg.svg'
import productImgIconParkOutlineVideoConference from '../assets/landing/figma-showcase-icon-park-outline-video-conference.svg'
import productImgContainer from '../assets/landing/figma-showcase-container.svg'
import productImgContainer1 from '../assets/landing/figma-showcase-container1.svg'
import productImgContainer2 from '../assets/landing/figma-showcase-container2.svg'
import productImgContainer3 from '../assets/landing/figma-showcase-container3.svg'
import productImgContainer4 from '../assets/landing/figma-showcase-container4.svg'
import productImgContainer5 from '../assets/landing/figma-showcase-container5.svg'
import productImgBoxiconsTarget from '../assets/landing/figma-showcase-boxicons-target.svg'
import productImgBasilDocumentOutline from '../assets/landing/figma-showcase-basil-document-outline.svg'
import preparationImgDashiconsArrowLeftAlt2 from '../assets/landing/figma-preparation-dashicons-arrow-left-alt2.svg'
import preparationImgDashiconsArrowRightAlt2 from '../assets/landing/figma-preparation-dashicons-arrow-right-alt2.svg'
import desktopImgContainer from '../assets/landing/figma-desktop-container.svg'
import desktopImgContainer1 from '../assets/landing/figma-desktop-container1.svg'
import desktopImgContainer2 from '../assets/landing/figma-desktop-container2.svg'
import privacyImgContainer from '../assets/landing/figma-privacy-container.svg'
import privacyImgContainer1 from '../assets/landing/figma-privacy-container1.svg'
import privacyImgContainer2 from '../assets/landing/figma-privacy-container2.svg'
import privacyImgContainer3 from '../assets/landing/figma-privacy-container3.svg'
import pricingImgRectangle1 from '../assets/landing/figma-pricing-rectangle1.svg'
import pricingImgContainer from '../assets/landing/figma-pricing-container.svg'
import pricingImgContainer1 from '../assets/landing/figma-pricing-container1.svg'
import pricingImgContainer2 from '../assets/landing/figma-pricing-container2.svg'
import faqImgContainer from '../assets/landing/figma-faq-container.svg'
import finalctaImgSaiiaIntelligentMascot from '../assets/landing/figma-cta-saiia-intelligent-mascot.png'
import finalctaImgContainer from '../assets/landing/figma-cta-container.svg'
import finalctaImgContainer1 from '../assets/landing/figma-cta-container1.svg'
import finalctaImgEllipse3 from '../assets/landing/figma-cta-ellipse3.svg'
import finalctaImgLine9 from '../assets/landing/figma-cta-line9.svg'
import finalctaImgLine10 from '../assets/landing/figma-cta-line10.svg'
import finalctaImgLine11 from '../assets/landing/figma-cta-line11.svg'
import finalctaImgLine12 from '../assets/landing/figma-cta-line12.svg'
import finalctaImgLine13 from '../assets/landing/figma-cta-line13.svg'
import finalctaImgLine14 from '../assets/landing/figma-cta-line14.svg'
import finalctaImgLine15 from '../assets/landing/figma-cta-line15.svg'
import finalctaImgLine16 from '../assets/landing/figma-cta-line16.svg'
import finalctaImgLine17 from '../assets/landing/figma-cta-line17.svg'
import finalctaImgLine18 from '../assets/landing/figma-cta-line18.svg'
import finalctaImgLine19 from '../assets/landing/figma-cta-line19.svg'
import finalctaImgLine20 from '../assets/landing/figma-cta-line20.svg'
import finalctaImgEllipse2 from '../assets/landing/figma-cta-ellipse2.svg'
import finalctaImgLine38 from '../assets/landing/figma-cta-line38.svg'
import finalctaImgLine39 from '../assets/landing/figma-cta-line39.svg'
import finalctaImgLine40 from '../assets/landing/figma-cta-line40.svg'
import finalctaImgLine41 from '../assets/landing/figma-cta-line41.svg'
import finalctaImgLine42 from '../assets/landing/figma-cta-line42.svg'
import finalctaImgLine43 from '../assets/landing/figma-cta-line43.svg'
import finalctaImgLine44 from '../assets/landing/figma-cta-line44.svg'
import finalctaImgLine45 from '../assets/landing/figma-cta-line45.svg'
import finalctaImgLine46 from '../assets/landing/figma-cta-line46.svg'
import finalctaImgLine47 from '../assets/landing/figma-cta-line47.svg'
import finalctaImgLine48 from '../assets/landing/figma-cta-line48.svg'
import finalctaImgLine49 from '../assets/landing/figma-cta-line49.svg'
import finalctaImgLine50 from '../assets/landing/figma-cta-line50.svg'
import headerImgContainer from '../assets/landing/figma-header-container.svg'
import headerImgContainer1 from '../assets/landing/figma-header-container1.svg'
import footerImgSaiiaAiLogo from '../assets/landing/figma-footer-saiia-ai-logo.png'

function Hero() {
  const cockpitRef = useRef(null);
  const [cardsEntered, setCardsEntered] = useState(false);

  useEffect(() => {
    const frame = cockpitRef.current;
    const mascot = frame.querySelector('[data-node-id="173:2462"]');
    const cards = frame.querySelectorAll('.hero-floating-card');
    const measure = () => {
      const bounds = frame.getBoundingClientRect();
      const center = mascot.getBoundingClientRect();
      cards.forEach(card => {
        card.style.setProperty('--hero-start-x', `${center.left + center.width / 2 - bounds.left - card.offsetLeft - card.offsetWidth / 2}px`);
        card.style.setProperty('--hero-start-y', `${center.top + center.height / 2 - bounds.top - card.offsetTop - card.offsetHeight / 2}px`);
      });
    };
    const resize = new ResizeObserver(measure);
    resize.observe(frame);
    cards.forEach(card => resize.observe(card));
    measure();
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        measure();
        setCardsEntered(true);
        observer.disconnect();
      }
    }, { threshold: 0.2 });
    observer.observe(frame);
    return () => { observer.disconnect(); resize.disconnect(); };
  }, []);

  return (
    <div className="figma-1" data-node-id="173:2434" data-name="Section - 1. HERO SECTION">
      <div className="figma-2" data-node-id="173:2435" data-name="Left Content">
        <div className="figma-3" data-node-id="173:2436" data-name="Context Pill">
          <div className="figma-4" data-node-id="173:2437" data-name="Background+Shadow" />
          <div className="figma-5" data-node-id="173:2438" data-name="Container">
            <div className="figma-6">
              <div className="figma-7" data-node-id="173:2439">
                <p className="figma-8">SMART AI INTERVIEW ASSISTANT • CONTEXT-AWARE INTELLIGENCE</p>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-9" data-node-id="173:2440" data-name="Heading 1 - Main Headline">
          <h1 className="figma-10" data-node-id="173:2441">
            <span className="figma-11">Walk into every</span>
            <span className="figma-12">interview prepared.</span>
          </h1>
        </div>
        <div className="figma-13" data-node-id="173:2442" data-name="Supporting Text">
          <div className="figma-14" data-node-id="173:2443">
            <p className="figma-15">AI that understands your resume, your target role, and your interview</p>
            <p className="figma-15">context — helping you prepare smarter, respond with precision, and learn</p>
            <p className="figma-16">from every conversation.</p>
          </div>
        </div>
        <div className="figma-17" data-node-id="173:2444" data-name="CTAs">
          <a href="/auth/signup" className="figma-18" data-node-id="173:2445" data-name="Link">
            <div className="figma-19" data-node-id="173:2446" data-name="Container">
              <div className="figma-20" data-node-id="173:2447">
                <p className="figma-21">Get Started</p>
              </div>
            </div>
            <div className="figma-22" data-node-id="173:2448" data-name="Container">
              <img alt="" className="figma-23" src={heroImgContainer} />
            </div>
          </a>
          <a href="#how-it-works" className="figma-24" data-node-id="173:2450" data-name="Link">
            <div className="figma-25" data-node-id="173:2451" data-name="Container">
              <img alt="" className="figma-23" src={heroImgContainer1} />
            </div>
            <div className="figma-5" data-node-id="173:2453" data-name="Container">
              <div className="figma-6">
                <div className="figma-26" data-node-id="173:2454">
                  <p className="figma-21">See How It Works</p>
                </div>
              </div>
            </div>
          </a>
        </div>
        <div className="figma-27" data-node-id="173:2455" data-name="Trust Micro-Message">
          <div className="figma-28" data-node-id="173:2456" data-name="Container">
            <img alt="" className="figma-23" src={heroImgContainer2} />
          </div>
          <div className="figma-19" data-node-id="173:2458" data-name="Container">
            <div className="figma-29" data-node-id="173:2459">
              <p className="figma-30">Resume-powered • Job-targeted • AI-assisted. Built around your actual context.</p>
            </div>
          </div>
        </div>
      </div>
      <div className="figma-31" data-node-id="173:2460" data-name="Right Hero Visual Composition">
        <div ref={cockpitRef} className={`figma-32${cardsEntered ? ' hero-cards-entered' : ''}`} data-node-id="173:2461" data-name="Interactive Cockpit Frame">
          <div className="figma-33 hero-floating-card" data-node-id="173:2466" data-name="Floating Card 1: Top Right - AI Guidance">
            <div className="figma-5" data-node-id="173:2467" data-name="Container">
              <div className="figma-34">
                <div className="figma-4" data-node-id="173:2468" data-name="Background+Shadow" />
                <div className="figma-19" data-node-id="173:2469" data-name="Container">
                  <div className="figma-35" data-node-id="173:2470">
                    <p className="figma-8">AI LIVE GUIDANCE</p>
                  </div>
                </div>
              </div>
            </div>
            <div className="figma-36" data-node-id="173:2471">
              <p className="figma-37">“Highlight your distributed systems</p>
              <p className="figma-37">experience in Go and latency</p>
              <p className="figma-38">optimizations when discussing this role.”</p>
            </div>
          </div>
          <div className="figma-39 hero-floating-card" data-node-id="173:2472" data-name="Floating Card 2: Bottom Left - Resume Source">
            <div className="figma-40" data-node-id="173:2473" data-name="Background+Border">
              <div className="figma-41">
                <div className="figma-42" data-node-id="173:2474" data-name="Container">
                  <img alt="" className="figma-23" src={heroImgContainer3} />
                </div>
              </div>
            </div>
            <div className="figma-5" data-node-id="173:2476" data-name="Container">
              <div className="figma-6">
                <div className="figma-43" data-node-id="173:2477" data-name="Container">
                  <div className="figma-44" data-node-id="173:2478">
                    <p className="figma-45">RESUME SOURCE</p>
                  </div>
                </div>
                <div className="figma-46" data-node-id="173:2479" data-name="Container">
                  <div className="figma-47" data-node-id="173:2480">
                    <p className="figma-30">✓ 4.2 MB PDF Indexed</p>
                  </div>
                </div>
                <div className="figma-48" data-node-id="173:2481" data-name="Margin">
                  <div className="figma-43" data-node-id="173:2482" data-name="Container">
                    <div className="figma-49" data-node-id="173:2483">
                      <p className="figma-50">Senior Software Eng</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-51 hero-floating-card" data-node-id="173:2484" data-name="Floating Card 3: Bottom Right - Target Role">
            <div className="figma-52" data-node-id="173:2485" data-name="Background+Border">
              <div className="figma-41">
                <div className="figma-53" data-node-id="173:2486" data-name="Container">
                  <img alt="" className="figma-23" src={heroImgContainer4} />
                </div>
              </div>
            </div>
            <div className="figma-5" data-node-id="173:2488" data-name="Container">
              <div className="figma-6">
                <div className="figma-43" data-node-id="173:2489" data-name="Container">
                  <div className="figma-54" data-node-id="173:2490">
                    <p className="figma-45">TARGET CONTEXT</p>
                  </div>
                </div>
                <div className="figma-46" data-node-id="173:2491" data-name="Container">
                  <div className="figma-47" data-node-id="173:2492">
                    <p className="figma-30">✓ Staff Backend @ Stripe</p>
                  </div>
                </div>
                <div className="figma-48" data-node-id="173:2493" data-name="Margin">
                  <div className="figma-43" data-node-id="173:2494" data-name="Container">
                    <div className="figma-49" data-node-id="173:2495">
                      <p className="figma-50">System Design • Concurrency</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-55" data-node-id="173:2462" data-name="Mascot Centerpiece">
            <div className="figma-56" data-node-id="173:2463" data-name="Container">
              <div className="figma-57" data-node-id="173:2464" data-name="Intervucopilot AI Mascot">
                <div className="figma-58">
                  <img alt="" className="figma-59" src={heroImgSaiiaAiMascot} />
                </div>
              </div>
              <div className="figma-60" data-node-id="173:2465" data-name="Overlay+Blur" />
            </div>
          </div>
        </div>
        <div className="figma-61" data-node-id="173:2496" style={{ backgroundImage: "linear-gradient(45.63932551093911deg, rgba(77, 141, 255, 0.15) 0%, rgba(169, 160, 255, 0.15) 100%)" }} data-name="Soft ambient radiant backdrop" />
        <div className="figma-62" data-node-id="173:2497" data-name="Dynamic Equation Bar:margin">
          <div className="figma-63" data-node-id="173:2498" data-name="Dynamic Equation Bar">
            <div className="figma-5" data-node-id="173:2499" data-name="Container">
              <div className="figma-64">
                <div className="figma-65" data-node-id="173:2500">
                  <p className="figma-8">RESUME</p>
                </div>
              </div>
            </div>
            <div className="figma-66" data-node-id="173:2501" data-name="Container">
              <div className="figma-67">
                <div className="figma-68" data-node-id="173:2502">
                  <p className="figma-69">+</p>
                </div>
              </div>
            </div>
            <div className="figma-5" data-node-id="173:2503" data-name="Container">
              <div className="figma-64">
                <div className="figma-65" data-node-id="173:2504">
                  <p className="figma-8">TARGET ROLE</p>
                </div>
              </div>
            </div>
            <div className="figma-66" data-node-id="186:459" data-name="Container">
              <div className="figma-67">
                <div className="figma-68" data-node-id="186:460">
                  <p className="figma-69">+</p>
                </div>
              </div>
            </div>
            <div className="figma-5" data-node-id="173:2507" data-name="Container">
              <div className="figma-64">
                <div className="figma-65" data-node-id="173:2508">
                  <p className="figma-8">LIVE CONTEXT</p>
                </div>
              </div>
            </div>
            <div className="figma-66" data-node-id="186:462" data-name="Container">
              <div className="figma-67">
                <div className="figma-68" data-node-id="186:463">
                  <p className="figma-69">=</p>
                </div>
              </div>
            </div>
            <div className="figma-70" data-node-id="173:2511" data-name="Background+Border">
              <div className="figma-71">
                <div className="figma-72" data-node-id="173:2512">
                  <p className="figma-8">Intervucopilot</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Problem() {
  return (
    <div className="figma-73" data-node-id="173:2513" data-name="Section - 2. THE PROBLEM SECTION">
      <div className="figma-74" data-node-id="173:2514" data-name="Container">
        <div className="figma-75" data-node-id="173:2515" data-name="Margin">
          <div className="figma-76" data-node-id="173:2516" data-name="Container">
            <div className="figma-77" data-node-id="173:2517">
              <p className="figma-78">THE PREPARATION GAP</p>
            </div>
          </div>
        </div>
        <div className="figma-79" data-node-id="173:2518">
          <p className="figma-80">{`Interviews shouldn't feel like guesswork.`}</p>
        </div>
        <div className="figma-81" data-node-id="173:2519" data-name="Margin">
          <div className="figma-82" data-node-id="173:2520" data-name="Container">
            <div className="figma-83" data-node-id="173:2521">
              <p className="figma-84">Interview preparation is often fragmented. Your resume, job description, preparation notes, and interview</p>
              <p className="figma-85">conversations live in completely disconnected places.</p>
            </div>
          </div>
        </div>
      </div>
      <div className="figma-86" data-node-id="185:3405" data-name="Section - 11. FINAL MEMORABLE CTA (Clean Light Theme with Blue Radiance):margin">
        <div className="figma-87" data-node-id="185:3406" data-name="Section - 11. FINAL MEMORABLE CTA (Clean Light Theme with Blue Radiance)">
          <div className="figma-88" data-node-id="185:3407" data-name="Background+Border+Shadow">
            <div className="figma-89" data-node-id="185:3408" data-name="Soft ambient glow" />
            <div className="figma-90" data-node-id="185:3412" data-name="Heading 2">
              <div className="figma-91" data-node-id="185:3413">
                <p className="figma-92">Your next interview starts</p>
                <p className="figma-93">
                  before you enter the room.
                  </p>
              </div>
            </div>
            <div className="figma-94" data-node-id="185:3417" data-name="Container">
              <div className="figma-95" data-node-id="185:3418" data-name="Link">
                <div className="figma-76" data-node-id="185:3419" data-name="Container">
                  <div className="figma-96" data-node-id="185:3420">
                    <p className="figma-21">Play Video</p>
                  </div>
                </div>
                <div className="figma-22" data-node-id="185:3421" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="figma-97" data-node-id="173:2522" data-name="4 Problem Cards Grid">
        <div className="figma-98" data-node-id="173:2523" data-name="Card 1">
          <div className="figma-99" data-node-id="173:2524" data-name="Container">
            <div className="figma-100">
              <div className="figma-101" data-node-id="173:2525" data-name="Background+Border">
                <div className="figma-102" data-node-id="173:2526" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer1} />
                </div>
              </div>
              <div className="figma-103" data-node-id="173:2528" data-name="Heading 3">
                <div className="figma-104" data-node-id="173:2529">
                  <p className="figma-105">Generic answers</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:2530" data-name="Container">
                <div className="figma-106" data-node-id="173:2531">
                  <p className="figma-107">Standard AI chatbots spit out generic behavioral scripts that lack the authenticity and depth of your lived career milestones.</p>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:2532" data-name="Margin">
            <div className="figma-108">
              <div className="figma-109" data-node-id="173:2533" data-name="HorizontalBorder">
                <div className="figma-110" data-node-id="173:2534" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer2} />
                </div>
                <div className="figma-5" data-node-id="173:2536" data-name="Container">
                  <div className="figma-6">
                    <div className="figma-111" data-node-id="173:2537">
                      <p className="figma-30">Zero profile awareness</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-112" data-node-id="173:2538" data-name="Card 2">
          <div className="figma-99" data-node-id="173:2539" data-name="Container">
            <div className="figma-100">
              <div className="figma-101" data-node-id="173:2540" data-name="Background+Border">
                <div className="figma-113" data-node-id="173:2541" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer3} />
                </div>
              </div>
              <div className="figma-103" data-node-id="173:2543" data-name="Heading 3">
                <div className="figma-104" data-node-id="173:2544">
                  <p className="figma-105">Scattered prep</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:2545" data-name="Container">
                <div className="figma-106" data-node-id="173:2546">
                  <p className="figma-114">Your resume, target rubrics, personal cheat sheets, and rehearsal bullet points exist in disparate browser tabs</p>
                  <p className="figma-107">and Notion docs.</p>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:2547" data-name="Margin">
            <div className="figma-108">
              <div className="figma-109" data-node-id="173:2548" data-name="HorizontalBorder">
                <div className="figma-110" data-node-id="173:2549" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer2} />
                </div>
                <div className="figma-5" data-node-id="173:2551" data-name="Container">
                  <div className="figma-6">
                    <div className="figma-111" data-node-id="173:2552">
                      <p className="figma-30">Constant tab toggling</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-115" data-node-id="173:2553" data-name="Card 3">
          <div className="figma-99" data-node-id="173:2554" data-name="Container">
            <div className="figma-100">
              <div className="figma-101" data-node-id="173:2555" data-name="Background+Border">
                <div className="figma-116" data-node-id="173:2556" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer4} />
                </div>
              </div>
              <div className="figma-103" data-node-id="173:2558" data-name="Heading 3">
                <div className="figma-104" data-node-id="173:2559">
                  <p className="figma-105">Lost takeaways</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:2560" data-name="Container">
                <div className="figma-106" data-node-id="173:2561">
                  <p className="figma-114">Critical technical follow-ups and</p>
                  <p className="figma-114">exact interviewer reactions</p>
                  <p className="figma-114">evaporate from your memory</p>
                  <p className="figma-107">seconds after hanging up the call.</p>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:2562" data-name="Margin">
            <div className="figma-108">
              <div className="figma-109" data-node-id="173:2563" data-name="HorizontalBorder">
                <div className="figma-110" data-node-id="173:2564" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer2} />
                </div>
                <div className="figma-5" data-node-id="173:2566" data-name="Container">
                  <div className="figma-6">
                    <div className="figma-111" data-node-id="173:2567">
                      <p className="figma-30">No post-call retention</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-117" data-node-id="173:2568" data-name="Card 4">
          <div className="figma-99" data-node-id="173:2569" data-name="Container">
            <div className="figma-100">
              <div className="figma-101" data-node-id="173:2570" data-name="Background+Border">
                <div className="figma-118" data-node-id="173:2571" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer5} />
                </div>
              </div>
              <div className="figma-103" data-node-id="173:2573" data-name="Heading 3">
                <div className="figma-104" data-node-id="173:2574">
                  <p className="figma-105">No role context</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:2575" data-name="Container">
                <div className="figma-106" data-node-id="173:2576">
                  <p className="figma-114">Blanket interview strategies miss the</p>
                  <p className="figma-114">mark by failing to adapt to level</p>
                  <p className="figma-114">expectations, whether L4 IC</p>
                  <p className="figma-114">execution or Staff architectural</p>
                  <p className="figma-107">tradeoffs.</p>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:2577" data-name="Margin">
            <div className="figma-108">
              <div className="figma-109" data-node-id="173:2578" data-name="HorizontalBorder">
                <div className="figma-110" data-node-id="173:2579" data-name="Container">
                  <img alt="" className="figma-23" src={problemImgContainer2} />
                </div>
                <div className="figma-5" data-node-id="173:2581" data-name="Container">
                  <div className="figma-6">
                    <div className="figma-111" data-node-id="173:2582">
                      <p className="figma-30">Misaligned seniorities</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const workflowDetails = [
  { label: 'Your Resume', chip: 'INPUT 01 • RESUME CONTEXT', title: 'Your experience becomes structured context.', description: 'Intervucopilot organizes skills, projects, achievements, and work history into information that can support more relevant preparation.', color: '#4d8dff', background: '#eff6ff', border: '#dbeafe' },
  { label: 'Target Role', chip: 'INPUT 02 • Role CONTEXT', title: 'Your preparation adapts to the role.', description: 'Job requirements and competencies provide context for targeted practice and role-specific preparation.', color: '#4f46e5', background: '#eef2ff', border: '#e0e7ff' },
  { label: 'Live Interview', chip: 'INPUT 03 • Interview CONTEXT', title: 'Relevant context during the session.', description: 'Access permitted session information and prepared material through the supported desktop companion workflow.', color: '#7c3aed', background: '#eff6ff', border: '#f5f3ff' },
  { label: 'AI Guidance', chip: 'outPUT 01 • Guidance CONTEXT', title: 'Guidance grounded in your experience.', description: 'Use role requirements and your own experience to explore relevant examples and structured preparation prompts.', color: '#4d8dff', background: '#eff6ff', border: '#dbeafe' },
  { label: 'Session Insights', chip: 'outPUT 02 • Insights CONTEXT', title: 'Learn from every interview.', description: 'Review takeaways, identify areas for improvement, and carry useful context into future preparation.', color: '#059669', background: '#ecfdf5', border: '#d1fae5' },
  { label: 'Intervucopilot core engine', chip: 'CORE ENGINE • Engine context', title: 'One engine connecting your interview context.', description: 'The Intervucopilot Engine brings resume information, target role requirements, and interview context together to support a coherent preparation workflow.', color: '#4d8dff', background: 'rgba(77,141,255,0.1)', border: 'rgba(77,141,255,0.3)' },
];

function Workflow() {
  const [activeWorkflowIndex, setActiveWorkflowIndex] = useState(0);
  const [isWorkflowHovered, setIsWorkflowHovered] = useState(false);
  const [isWorkflowFocused, setIsWorkflowFocused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const isWorkflowPaused = isWorkflowHovered || isWorkflowFocused;
  const detail = workflowDetails[activeWorkflowIndex];
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(media.matches);
    media.addEventListener('change', update);
    update();
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (isWorkflowPaused || reducedMotion) return;
    const interval = window.setInterval(() => setActiveWorkflowIndex(index => (index + 1) % 5), 2000);
    return () => window.clearInterval(interval);
  }, [isWorkflowPaused, reducedMotion, activeWorkflowIndex]);
  const workflowNode = index => ({
    role: 'button', tabIndex: 0, 'aria-label': workflowDetails[index].label,
    'aria-pressed': activeWorkflowIndex === index, 'aria-controls': 'workflow-detail',
    onClick: () => setActiveWorkflowIndex(index),
    onKeyDown: event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        setActiveWorkflowIndex(index);
      }
    },
  });
  return (
    <div className="figma-73" data-node-id="173:2583" data-name="Section - 3. SOLUTION / WORKFLOW PIPELINE"
      onMouseEnter={() => setIsWorkflowHovered(true)} onMouseLeave={() => setIsWorkflowHovered(false)}
      onFocusCapture={() => setIsWorkflowFocused(true)}
      onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) setIsWorkflowFocused(false); }}>
      <div className="figma-76" data-node-id="173:2584" data-name="Container">
        <div className="figma-79" data-node-id="173:2591">
          <p className="figma-80">Your entire interview journey. One intelligent AI.</p>
        </div>
        <div className="figma-81" data-node-id="173:2592" data-name="Margin">
          <div className="figma-119" data-node-id="173:2593" data-name="Container">
            <div className="figma-83" data-node-id="173:2594">
              <p className="figma-85">From resume analysis to personalized interview guidance, Intervucopilot connects every step to help you prepare with confidence.</p>
            </div>
          </div>
        </div>
      </div>
      <div className="figma-120" data-node-id="267:7599" data-name="ARCHITECTURE DIAGRAM CONTAINER">
        <div className="figma-121" data-node-id="267:7600" data-name="Diagrame container">
          <div className="figma-122">
            <div className="figma-123" data-node-id="I267:7600;258:5277" data-name="Main System Architecture Grid (Inputs -> Core Engine -> Outputs)">
              <div className="figma-124" data-node-id="I267:7600;258:5278" data-name="LEFT COLUMN: INPUTS (3 vertical cards)">
                <div className="figma-125" data-node-id="I267:7600;258:5279" data-name="Margin">
                  <div className="figma-126" data-node-id="I267:7600;258:5280" data-name="Container">
                    <div className="figma-19" data-node-id="I267:7600;258:5281" data-name="Container">
                      <div className="figma-127" data-node-id="I267:7600;258:5282">
                        <p className="figma-8">CANDIDATE INPUTS</p>
                      </div>
                    </div>
                    <div className="figma-128" data-node-id="I267:7600;258:5283" data-name="Background+Border">
                      <div className="figma-129" data-node-id="I267:7600;258:5284">
                        <p className="figma-8">3 Streams</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-130 workflow-node" {...workflowNode(0)} data-node-id="I267:7600;258:5285" data-name="Button - Input 01: Resume">
                  <div className="figma-99" data-node-id="I267:7600;258:5286" data-name="Container">
                    <div className="figma-131">
                      <div className="figma-132" data-node-id="I267:7600;258:5287" data-name="Container">
                        <div className="figma-133" data-node-id="I267:7600;258:5288" data-name="Background+Border">
                          <div className="figma-42" data-node-id="I267:7600;258:5289" data-name="Container">
                            <img alt="" className="figma-23" src={workflowImgContainer} />
                          </div>
                        </div>
                        <div className="figma-134" data-node-id="I267:7600;258:5291" data-name="Paragraph">
                          <div className="figma-135" data-node-id="I267:7600;258:5292">
                            <p className="figma-45">INPUT 01</p>
                          </div>
                          <div className="figma-136" data-node-id="I267:7600;258:5293">
                            <p className="figma-137">Your Resume</p>
                          </div>
                        </div>
                      </div>
                      <div className="figma-138" data-node-id="I267:7600;258:5294" data-name="Background+Border">
                        <div className="figma-139" data-node-id="I267:7600;258:5295" data-name="Background" />
                        <div className="figma-140" data-node-id="I267:7600;258:5296">
                          <p className="figma-8">Resume indexed</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="I267:7600;258:5297" data-name="Container">
                    <div className="figma-6">
                      <div className="figma-141" data-node-id="I267:7600;258:5298">
                        <p className="figma-142">Parse, index, and organize your experience, skills,</p>
                        <p className="figma-143">achievements, and project history into structured interview ready context.</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-144 workflow-node" {...workflowNode(1)} data-node-id="I267:7600;258:5299" data-name="Button - Input 02: Target Role">
                  <div className="figma-99" data-node-id="I267:7600;258:5300" data-name="Container">
                    <div className="figma-131">
                      <div className="figma-132" data-node-id="I267:7600;258:5301" data-name="Container">
                        <div className="figma-145" data-node-id="I267:7600;258:5302" data-name="Background+Border">
                          <div className="figma-25" data-node-id="I267:7600;258:5303" data-name="Container">
                            <img alt="" className="figma-23" src={workflowImgContainer1} />
                          </div>
                        </div>
                        <div className="figma-146" data-node-id="I267:7600;258:5305" data-name="Paragraph">
                          <div className="figma-147" data-node-id="I267:7600;258:5306">
                            <p className="figma-45">INPUT 02</p>
                          </div>
                          <div className="figma-136" data-node-id="I267:7600;258:5307">
                            <p className="figma-137">Target Role</p>
                          </div>
                        </div>
                      </div>
                      <div className="figma-138" data-node-id="I267:7600;258:5308" data-name="Background+Border">
                        <div className="figma-139" data-node-id="I267:7600;258:5309" data-name="Background" />
                        <div className="figma-148" data-node-id="I267:7600;258:5310">
                          <p className="figma-8">Role mapped</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="I267:7600;258:5311" data-name="Container">
                    <div className="figma-6">
                      <div className="figma-149" data-node-id="I267:7600;258:5312">
                        <p className="figma-142">Analyze the job description, required competencies,</p>
                        <p className="figma-143">technical skills, and role-specific expectations.</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-150 workflow-node" {...workflowNode(2)} data-node-id="I267:7600;258:5313" data-name="Button - Input 03: Live Interview">
                  <div className="figma-99" data-node-id="I267:7600;258:5314" data-name="Container">
                    <div className="figma-131">
                      <div className="figma-132" data-node-id="I267:7600;258:5315" data-name="Container">
                        <div className="figma-151" data-node-id="I267:7600;258:5316" data-name="Background+Border">
                          <div className="figma-152" data-node-id="I267:7600;258:5317" data-name="Container">
                            <img alt="" className="figma-23" src={workflowImgContainer2} />
                          </div>
                        </div>
                        <div className="figma-146" data-node-id="I267:7600;258:5319" data-name="Paragraph">
                          <div className="figma-153" data-node-id="I267:7600;258:5320">
                            <p className="figma-45">INPUT 03</p>
                          </div>
                          <div className="figma-136" data-node-id="I267:7600;258:5321">
                            <p className="figma-137">Live Interview</p>
                          </div>
                        </div>
                      </div>
                      <div className="figma-154" data-node-id="I267:7600;258:5322" data-name="Background+Border">
                        <div className="figma-155" data-node-id="I267:7600;258:5323" data-name="Background" />
                        <div className="figma-156" data-node-id="I267:7600;258:5324">
                          <p className="figma-8">Session ready</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="I267:7600;258:5325" data-name="Container">
                    <div className="figma-6">
                      <div className="figma-149" data-node-id="I267:7600;258:5326">
                        <p className="figma-143">Uses permitted interview context and available audio or session information to support relevant preparation and contextual assistance.</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="figma-157" data-node-id="I267:7600;258:5327" data-name="CENTER COLUMN: CORE Intervucopilot ENGINE (Dominant center anchor)">
                <div className="figma-158 workflow-engine" {...workflowNode(5)} data-node-id="I267:7600;258:5328" data-name="Button">
                  <div className="figma-159" data-node-id="I267:7600;258:5329" data-name="Mascot Avatar:margin">
                    <div className="figma-160" data-node-id="I267:7600;258:5330" data-name="Mascot Avatar">
                      <div className="figma-161" data-node-id="I267:7600;258:5331" data-name="Intervucopilot Core Engine">
                        <div className="figma-162">
                          <img alt="" className="figma-163" src={workflowImgSaiiaCoreEngine} />
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-164" data-node-id="I267:7600;258:5332" data-name="Badge:margin">
                    <div className="figma-165" data-node-id="I267:7600;258:5333" data-name="Badge">
                      <div className="figma-166" data-node-id="I267:7600;258:5334" data-name="Background+Shadow" />
                      <div className="figma-5" data-node-id="I267:7600;258:5335" data-name="Container">
                        <div className="figma-64">
                          <div className="figma-167" data-node-id="I267:7600;258:5336">
                            <p className="figma-168">CORE ENGINE</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-75" data-node-id="I267:7600;258:5337" data-name="Heading 3:margin">
                    <div className="figma-76" data-node-id="I267:7600;258:5338" data-name="Heading 3">
                      <div className="figma-169" data-node-id="I267:7600;258:5339">
                        <p className="figma-170">Intervucopilot</p>
                      </div>
                    </div>
                  </div>
                  <div className="figma-171" data-node-id="I267:7600;258:5340" data-name="Margin">
                    <div className="figma-172" data-node-id="I267:7600;258:5341">
                      <p className="figma-173">Connects your experience, target role, and</p>
                      <p className="figma-173">interview context to generate relevant,</p>
                      <p className="figma-174">personalized preparation intelligence.</p>
                    </div>
                  </div>
                  <div className="figma-175" data-node-id="I267:7600;258:5342" data-name="Status Tag">
                    <div className="figma-176" data-node-id="I267:7600;258:5343" data-name="Container">
                      <img alt="" className="figma-23" src={workflowImgContainer3} />
                    </div>
                    <div className="figma-5" data-node-id="I267:7600;258:5345" data-name="Container">
                      <div className="figma-64">
                        <div className="figma-177" data-node-id="I267:7600;258:5346">
                          <p className="figma-78">Context synchronized</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="figma-178" data-node-id="I267:7600;258:5347" data-name="RIGHT COLUMN: OUTPUTS (2 vertical cards)">
                <div className="figma-125" data-node-id="I267:7600;258:5348" data-name="Margin">
                  <div className="figma-126" data-node-id="I267:7600;258:5349" data-name="Container">
                    <div className="figma-19" data-node-id="I267:7600;258:5350" data-name="Container">
                      <div className="figma-127" data-node-id="I267:7600;258:5351">
                        <p className="figma-8">INTELLIGENT OUTPUTS</p>
                      </div>
                    </div>
                    <div className="figma-179" data-node-id="I267:7600;258:5352" data-name="Background+Border">
                      <div className="figma-180" data-node-id="I267:7600;258:5353">
                        <p className="figma-8">Real-Time Results</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-181 workflow-node" {...workflowNode(3)} data-node-id="I267:7600;258:5354" data-name="Button - Output 01: AI Guidance">
                  <div className="figma-99" data-node-id="I267:7600;258:5355" data-name="Container">
                    <div className="figma-131">
                      <div className="figma-132" data-node-id="I267:7600;258:5356" data-name="Container">
                        <div className="figma-133" data-node-id="I267:7600;258:5357" data-name="Background+Border">
                          <div className="figma-182" data-node-id="I267:7600;258:5358" data-name="Container">
                            <img alt="" className="figma-23" src={workflowImgContainer4} />
                          </div>
                        </div>
                        <div className="figma-146" data-node-id="I267:7600;258:5360" data-name="Paragraph">
                          <div className="figma-135" data-node-id="I267:7600;258:5361">
                            <p className="figma-45">OUTPUT 01</p>
                          </div>
                          <div className="figma-136" data-node-id="I267:7600;258:5362">
                            <p className="figma-137">AI Guidance</p>
                          </div>
                        </div>
                      </div>
                      <div className="figma-138" data-node-id="I267:7600;258:5363" data-name="Background+Border">
                        <div className="figma-139" data-node-id="I267:7600;258:5364" data-name="Background" />
                        <div className="figma-148" data-node-id="I267:7600;258:5365">
                          <p className="figma-8">Personalized guidance</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="I267:7600;258:5366" data-name="Container">
                    <div className="figma-6">
                      <div className="figma-149" data-node-id="I267:7600;258:5367">
                        <p className="figma-142">Provides role-specific preparation prompts, relevant</p>
                        <p className="figma-143">{`experience references, and structured guidance grounded in the candidate's context.`}</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-181 workflow-node" {...workflowNode(4)} data-node-id="I267:7600;258:5368" data-name="Button - Output 02: Session Insights">
                  <div className="figma-99" data-node-id="I267:7600;258:5369" data-name="Container">
                    <div className="figma-183">
                      <div className="figma-132" data-node-id="I267:7600;258:5370" data-name="Container">
                        <div className="figma-184" data-node-id="I267:7600;258:5371" data-name="Background+Border">
                          <div className="figma-185" data-node-id="I267:7600;258:5372" data-name="Container">
                            <img alt="" className="figma-23" src={workflowImgContainer5} />
                          </div>
                        </div>
                        <div className="figma-146" data-node-id="I267:7600;258:5374" data-name="Paragraph">
                          <div className="figma-186" data-node-id="I267:7600;258:5375">
                            <p className="figma-45">OUTPUT 02</p>
                          </div>
                          <div className="figma-136" data-node-id="I267:7600;258:5376">
                            <p className="figma-137">Session Insights</p>
                          </div>
                        </div>
                      </div>
                      <div className="figma-138" data-node-id="I267:7600;258:5377" data-name="Background+Border">
                        <div className="figma-139" data-node-id="I267:7600;258:5378" data-name="Background" />
                        <div className="figma-148" data-node-id="I267:7600;258:5379">
                          <p className="figma-8">Insights organized</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="I267:7600;258:5380" data-name="Container">
                    <div className="figma-6">
                      <div className="figma-149" data-node-id="I267:7600;258:5381">
                        <p className="figma-143">Organizes interview takeaways, strengths, improvement areas, and follow-up preparation into a reusable learning history.</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="figma-187" data-node-id="I267:7600;258:5383" data-name="SHARED INTERACTIVE CONTEXT DETAIL PANEL">
              <div className="figma-188" id="workflow-detail" aria-live={isWorkflowPaused || reducedMotion ? 'polite' : 'off'} aria-atomic="true" data-node-id="I267:7600;258:5384" data-name="Background+Border+Shadow">
                <div className="figma-189">
                  <div className="figma-5" data-node-id="I267:7600;258:5385" data-name="Container">
                    <div className="figma-190">
                      <div className="figma-191 workflow-detail-content" key={activeWorkflowIndex} data-node-id="I267:7600;258:5389" data-name="Container">
                        <div className="figma-192" data-node-id="I267:7600;258:5390" data-name="Container">
                          <div className="figma-193" style={{ backgroundColor: detail.background, borderColor: detail.border }} data-node-id="I267:7600;258:5391" data-name="Background+Border">
                            <div className="figma-44" style={{ color: detail.color }} data-node-id="I267:7600;258:5392">
                              <p className="figma-45">{detail.chip}</p>
                            </div>
                          </div>
                          <div className="figma-19" data-node-id="I267:7600;258:5393" data-name="Container">
                            <div className="figma-194" data-node-id="I267:7600;258:5394">
                              <p className="figma-8">Interactive Deep-Dive</p>
                            </div>
                          </div>
                        </div>
                        <div className="figma-195" data-node-id="I267:7600;258:5395" data-name="Heading 4">
                          <div className="figma-196" data-node-id="I267:7600;258:5396">
                              <p className="figma-105">{detail.title}</p>
                          </div>
                        </div>
                        <div className="figma-197" data-node-id="I267:7600;258:5397" data-name="Container">
                          <div className="figma-198" data-node-id="I267:7600;258:5398">
                            <p className="figma-107">{detail.description}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-199" data-node-id="I267:7600;258:5399" data-name="Background+Border">
                    <div className="figma-200">
                      <div className="figma-201" data-node-id="I267:7600;258:5400" data-name="Container">
                        <img alt="" className="figma-23" src={workflowImgContainer6} />
                      </div>
                      <div className="figma-5" data-node-id="I267:7600;258:5402" data-name="Container">
                        <div className="figma-6">
                          <div className="figma-202" data-node-id="I267:7600;258:5403">
                            <p className="figma-203">Click any node to explore</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const featureTabFrames = [
  {"id":"269:13876","cards":[{"id":"I269:13874;269:13576","number":"04","x":0,"y":236,"width":688,"height":360,"text":[{"text":"04","x":39.228515625,"y":52.25,"width":22,"height":23},{"text":"Know what to practice before the next round.","x":30.228515625,"y":96.5,"width":264,"height":54},{"text":"Get structured practice questions, relevant technical topics, and follow-up prompts tailored to your target role and experience.","x":30.228515625,"y":162.5,"width":264,"height":91},{"text":"AI follow-ups and answer refinement","x":52.89453125,"y":297.5,"width":198,"height":18}],"art":{"id":"I269:13874;269:13591","name":"search/cuate","x":318.228515625,"y":62.999267578125,"width":339.544677734375,"height":234.00146484375},"icon":{"id":"I269:13874;269:13587","x":30.228515625,"y":300.183349609375,"width":14.666666984558105,"height":12.633333206176758}},{"id":"I269:13874;267:11943","number":"01","x":738,"y":216,"width":738,"height":400,"text":[{"text":"01","x":50.779296875,"y":82.25,"width":22,"height":23},{"text":"Turn your experience into interview-ready answers.","x":39.279296875,"y":129,"width":307,"height":54},{"text":"Intervucopilot extracts your skills, projects, achievements, and work history to build a personal knowledge base for interview preparation.","x":39.279296875,"y":195,"width":307,"height":91},{"text":"Automatic parsing • PDF, DOCX, TXT","x":59.279296875,"y":310,"width":231,"height":18}],"art":{"id":"I269:13874;267:11958","name":"documents/amico","x":403.279296875,"y":82.2576904296875,"width":295.4425964355469,"height":235.4845733642578},"icon":{"id":"I269:13874;267:11954","x":39.279296875,"y":311.5,"width":12,"height":15}},{"id":"I269:13874;267:12065","number":"02","x":1526,"y":236,"width":688,"height":360,"text":[{"text":"02","x":61.17578125,"y":52.25,"width":21,"height":23},{"text":"Prepare for the role, not just the interview.","x":51.67578125,"y":96.5,"width":285,"height":54},{"text":"Add a job description to identify required skills, technical expectations, and role-specific competencies. Focus your preparation on what matters for the position.","x":51.67578125,"y":162.5,"width":285,"height":91},{"text":"Job requirements mapped","x":69.009765625,"y":297.5,"width":167,"height":18}],"art":{"id":"I269:13874;267:12080","name":"mobile-login/amico","x":360.67578125,"y":51.9998779296875,"width":275.64794921875,"height":256.0002136230469},"icon":{"id":"I269:13874;267:12076","x":51.67578125,"y":299.83331298828125,"width":9.333333015441895,"height":13.333333015441895}}]},
  {"id":"269:19136","cards":[{"id":"I269:14975;269:13874;267:11225","number":"01","x":0,"y":236,"width":688,"height":360,"text":[{"text":"01","x":41.779296875,"y":52.25,"width":18,"height":23},{"text":"Turn your experience into interview-ready answers.","x":30.779296875,"y":96.5,"width":307,"height":54},{"text":"Intervucopilot extracts your skills, projects, achievements, and work history to build a personal knowledge base for interview preparation.","x":30.779296875,"y":162.5,"width":307,"height":91},{"text":"Automatic parsing • PDF, DOCX, TXT","x":49.4453125,"y":297.5,"width":198,"height":18}],"art":{"id":"I269:14975;269:13874;267:11240","name":"documents/amico","x":361.779296875,"y":62.2579345703125,"width":295.4425964355469,"height":235.4844512939453},"icon":{"id":"I269:14975;269:13874;267:11236","x":30.779296875,"y":299.8333740234375,"width":10.666666984558105,"height":13.333333015441895}},{"id":"I269:14975;269:13874;267:11349","number":"02","x":738,"y":216,"width":738,"height":400,"text":[{"text":"02","x":53.025390625,"y":60.75,"width":26,"height":23},{"text":"Prepare for the role, not just the interview.","x":43.525390625,"y":107.5,"width":285,"height":54},{"text":"Add a job description to identify required skills, technical expectations, and role-specific competencies. Focus your preparation on what matters for the position.","x":43.525390625,"y":173.5,"width":285,"height":114},{"text":"Job requirements mapped","x":61.525390625,"y":331.5,"width":267,"height":18}],"art":{"id":"I269:14975;269:13874;267:11364","name":"mobile-login/amico","x":386.525390625,"y":57,"width":307.9501953125,"height":285.9998779296875},"icon":{"id":"I269:14975;269:13874;267:11360","x":43.525390625,"y":333,"width":10,"height":15}},{"id":"I269:14975;269:13874;267:11468","number":"03","x":1526,"y":236,"width":688,"height":360,"text":[{"text":"03","x":34.22265625,"y":52.25,"width":21,"height":23},{"text":"Stay grounded when the interview gets tough.","x":24.72265625,"y":96.5,"width":307.3399963378906,"height":54},{"text":"Use the desktop companion to access relevant resume context and concise memory cues during permitted interview sessions, without interrupting your conversation.","x":24.72265625,"y":162.5,"width":307,"height":91},{"text":"Desktop companion with minimal HUD","x":48.72265625,"y":297.5,"width":207,"height":18}],"art":{"id":"I269:14975;269:13874;267:11483","name":"devices/rafiki","x":355.72265625,"y":43.94482421875,"width":307.556640625,"height":272.1106872558594},"icon":{"id":"I269:14975;269:13874;267:11479","x":24.72265625,"y":300.8333740234375,"width":16,"height":11.333333015441895}}]},
  {"id":"269:19137","cards":[{"id":"I269:15525;269:13874;269:13079","number":"02","x":0,"y":236,"width":688,"height":360,"text":[{"text":"02","x":61.17578125,"y":52.25,"width":21,"height":23},{"text":"Prepare for the role, not just the interview.","x":51.67578125,"y":96.5,"width":285,"height":54},{"text":"Add a job description to identify required skills, technical expectations, and role-specific competencies. Focus your preparation on what matters for the position.","x":51.67578125,"y":162.5,"width":285,"height":91},{"text":"Role rubric alignment calibrated","x":69.009765625,"y":297.5,"width":175,"height":18}],"art":{"id":"I269:15525;269:13874;269:13094","name":"mobile-login/amico","x":360.67578125,"y":51.9998779296875,"width":275.64794921875,"height":256.0005798339844},"icon":{"id":"I269:15525;269:13874;269:13090","x":51.67578125,"y":299.833251953125,"width":9.333333015441895,"height":13.333333015441895}},{"id":"I269:15525;269:13874;267:10697","number":"03","x":738,"y":216,"width":738,"height":400,"text":[{"text":"03","x":47.8515625,"y":60.75,"width":26,"height":23},{"text":"Stay grounded when the interview gets tough.","x":38.3515625,"y":107.5,"width":307.3399963378906,"height":54},{"text":"Use the desktop companion to access relevant resume context and concise memory cues during permitted interview sessions, without interrupting your conversation.","x":38.3515625,"y":173.5,"width":307,"height":114},{"text":"Desktop companion with minimal HUD","x":64.3515625,"y":331.5,"width":207,"height":18}],"art":{"id":"I269:15525;269:13874;267:10712","name":"devices/rafiki","x":369.3515625,"y":69.4464111328125,"width":330.296875,"height":261.1071472167969},"icon":{"id":"I269:15525;269:13874;267:10708","x":38.3515625,"y":334,"width":18,"height":13}},{"id":"I269:15525;269:13874;267:10925","number":"04","x":1526,"y":236,"width":688,"height":360,"text":[{"text":"04","x":39.228515625,"y":52.25,"width":22,"height":23},{"text":"Know what to practice before the next round.","x":30.228515625,"y":96.5,"width":264,"height":54},{"text":"Get structured practice questions, relevant technical topics, and follow-up prompts tailored to your target role and experience.","x":30.228515625,"y":162.5,"width":264,"height":91},{"text":"AI follow-ups and answer refinement","x":52.89453125,"y":297.5,"width":198,"height":18}],"art":{"id":"I269:15525;269:13874;267:10940","name":"search/cuate","x":318.228515625,"y":62.999267578125,"width":339.544677734375,"height":234.00152587890625},"icon":{"id":"I269:15525;269:13874;267:10936","x":30.228515625,"y":300.183349609375,"width":14.666666984558105,"height":12.633333206176758}}]},
  {"id":"269:19138","cards":[{"id":"I269:16075;269:13874;269:13347","number":"03","x":0,"y":236,"width":688,"height":360,"text":[{"text":"03","x":34.22265625,"y":52.25,"width":21,"height":23},{"text":"Stay grounded when the interview gets tough.","x":24.72265625,"y":96.5,"width":307.3399963378906,"height":54},{"text":"Use the desktop companion to access relevant resume context and concise memory cues during permitted interview sessions, without interrupting your conversation.","x":24.72265625,"y":162.5,"width":307,"height":91},{"text":"Desktop companion with minimal HUD","x":48.72265625,"y":297.5,"width":207,"height":18}],"art":{"id":"I269:16075;269:13874;269:13362","name":"devices/rafiki","x":355.72265625,"y":43.944580078125,"width":307.556640625,"height":272.1109313964844},"icon":{"id":"I269:16075;269:13874;269:13358","x":24.72265625,"y":300.833251953125,"width":16,"height":11.333333015441895}},{"id":"I269:16075;269:13874;267:9926","number":"04","x":738,"y":216,"width":738,"height":400,"text":[{"text":"04","x":50.078125,"y":72.25,"width":26,"height":23},{"text":"Know what to practice before the next round.","x":40.578125,"y":119,"width":264,"height":54},{"text":"Get structured practice questions, relevant technical topics, and follow-up prompts tailored to your target role and experience.","x":40.578125,"y":185,"width":264,"height":91},{"text":"AI follow-ups and answer refinement","x":65.578125,"y":320,"width":231,"height":18}],"art":{"id":"I269:16075;269:13874;267:9941","name":"search/cuate","x":328.578125,"y":72.9033203125,"width":368.84375,"height":254.19313049316406},"icon":{"id":"I269:16075;269:13874;267:9937","x":40.578125,"y":321.5,"width":17,"height":15}},{"id":"I269:16075;269:13874;269:13203","number":"01","x":1526,"y":236,"width":688,"height":360,"text":[{"text":"01","x":41.779296875,"y":52.25,"width":18,"height":23},{"text":"Turn your experience into interview-ready answers.","x":30.779296875,"y":96.5,"width":307,"height":54},{"text":"Intervucopilot extracts your skills, projects, achievements, and work history to build a personal knowledge base for interview preparation.","x":30.779296875,"y":162.5,"width":307,"height":91},{"text":"Automatic parsing • PDF, DOCX, TXT","x":49.4453125,"y":297.5,"width":198,"height":18}],"art":{"id":"I269:16075;269:13874;269:13218","name":"documents/amico","x":361.779296875,"y":62.2578125,"width":295.4425964355469,"height":235.4845733642578},"icon":{"id":"I269:16075;269:13874;269:13214","x":30.779296875,"y":299.833251953125,"width":10.666666984558105,"height":13.333333015441895}}]},
];

const featureTabAssets = import.meta.glob('../assets/landing/feature-tab-*.svg', { eager: true, query: '?url', import: 'default' });
const featureTabNames = ['Resume', 'Job Match', 'Live Assist', 'AI Guidance'];

function FeatureTabSilderBar({ className }) {
  const [activePrepTabIndex, setActivePrepTabIndex] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(media.matches);
    media.addEventListener('change', update);
    update();
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (reducedMotion) return;
    const interval = window.setInterval(() => setActivePrepTabIndex(index => (index + 1) % 4), 2000);
    return () => window.clearInterval(interval);
  }, [activePrepTabIndex, reducedMotion]);
  const position = geometry => ({ left: geometry.x, top: geometry.y, width: geometry.width, height: geometry.height });
  return (
    <div className={className || 'figma-653'} data-node-id={featureTabFrames[activePrepTabIndex].id}>
      <div className="figma-248 feature-tab-cards" key={activePrepTabIndex}>
        {featureTabFrames[activePrepTabIndex].cards.map((card, slot) => {
          const active = slot === 1;
          const kind = active ? 'active' : 'side';
          const asset = name => featureTabAssets[`../assets/landing/feature-tab-${card.number}-${kind}${name}.svg`];
          const [number, title, body, footer] = card.text;
          const badgeSize = active ? 45 : 40;
          const statusIcon = card.number === '03' ? asset('-icon') :
            ({ '01': featuresImgContainer1, '02': featuresImgContainer2, '04': featuresImgContainer })[card.number];
          return (
            <div className={active ? 'figma-223' : 'feature-tab-side'} key={slot}>
              {active && <div className="figma-224" aria-hidden="true" />}
              <article className={`feature-tab-card ${active ? 'feature-tab-card-active' : ''}`}
                style={{ width: card.width, height: card.height }} data-card-number={card.number}
                data-node-id={card.id} role={active ? 'tabpanel' : undefined}
                id={active ? 'feature-tab-panel' : undefined}
                aria-labelledby={active ? `feature-tab-${activePrepTabIndex}` : undefined}>
                <span className="feature-tab-number" style={{
                  left: number.x + number.width / 2 - badgeSize / 2,
                  top: number.y + number.height / 2 - badgeSize / 2,
                  width: badgeSize, height: badgeSize,
                }}>{card.number}</span>
                <h3 className="feature-tab-title" style={position(title)}>{title.text}</h3>
                <p className="feature-tab-body" style={position(body)}>{body.text}</p>
                <img className="feature-tab-status-icon" src={statusIcon} alt="" style={position(card.icon)} />
                <p className="feature-tab-footer" style={{ ...position(footer), width: card.width - footer.x - 25 }}>{footer.text}</p>
                <img className="feature-tab-art" src={asset('')} alt="" style={position(card.art)} />
              </article>
            </div>
          );
        })}
      </div>
      <div className="figma-249 feature-tab-list" role="tablist" aria-label="Preparation features">
        <div className="figma-250" aria-hidden="true" style={{ left: 12 + activePrepTabIndex * 191 }} />
        {featureTabNames.map((name, index) => (
          <button type="button" className={`figma-${[251, 253, 255, 256][index]} feature-tab-button`}
            key={name} id={`feature-tab-${index}`} role="tab"
            aria-selected={index === activePrepTabIndex} aria-controls="feature-tab-panel"
            onClick={() => setActivePrepTabIndex(index)}
            onKeyDown={event => {
              let next;
              if (event.key === 'ArrowRight') next = (index + 1) % 4;
              if (event.key === 'ArrowLeft') next = (index + 3) % 4;
              if (event.key === 'Home') next = 0;
              if (event.key === 'End') next = 3;
              if (next !== undefined) {
                event.preventDefault();
                setActivePrepTabIndex(next);
                event.currentTarget.parentElement.querySelectorAll('[role="tab"]')[next].focus({ preventScroll: true });
              }
            }}>
            <span className="figma-254">{name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function Features() {
  return (
    <div className="figma-73" data-node-id="173:2668" data-name="Section - 4. BENTO FEATURE HIGHLIGHTS">
      <div className="figma-76" data-node-id="173:2669" data-name="Container">
        <div className="figma-75" data-node-id="173:2670" data-name="Margin">
          <div className="figma-76" data-node-id="173:2671" data-name="Container">
            <div className="figma-77" data-node-id="173:2672">
              <p className="figma-78">BESPOKE PREPARATION</p>
            </div>
          </div>
        </div>
        <div className="figma-79" data-node-id="173:2673">
          <p className="figma-80">Everything you need to prepare smarter.</p>
        </div>
        <div className="figma-81" data-node-id="173:2674" data-name="Margin">
          <div className="figma-257" data-node-id="173:2675" data-name="Container">
            <div className="figma-83" data-node-id="173:2676">
              <p className="figma-85">From deep resume ingestion to post-interview reflection, Intervucopilot keeps your preparation completely coherent.</p>
            </div>
          </div>
        </div>
      </div>
      <FeatureTabSilderBar className="figma-258" />
    </div>
  );
}

function CibHackerrank({ className }) {
  return (
    <div className={className || "figma-654"} data-node-id="220:616" data-name="cib:hackerrank">
      <img alt="" className="figma-23" src={platformsImgCibHackerrank} />
    </div>
  );
}

function LogosMicrosoftTeams({ className }) {
  return (
    <div className={className || "figma-655"} data-node-id="220:636" data-name="logos:microsoft-teams">
      <img alt="" className="figma-23" src={platformsImgLogosMicrosoftTeams} />
    </div>
  );
}

function SelfhstGoogleMeet({ className }) {
  return (
    <div className={className || "figma-654"} data-node-id="221:644" data-name="selfhst:google-meet">
      <img alt="" className="figma-23" src={platformsImgSelfhstGoogleMeet} />
    </div>
  );
}

function Fa7BrandsZoom({ className }) {
  return (
    <div className={className || "figma-656"} data-node-id="221:661" data-name="fa7-brands:zoom">
      <img alt="" className="figma-23" src={platformsImgFa7BrandsZoom} />
    </div>
  );
}

function AkarIconsZoomFill({ className }) {
  return (
    <div className={className || "figma-654"} data-node-id="221:652" data-name="akar-icons:zoom-fill">
      <div className="figma-259" data-node-id="221:646" data-name="Group">
        <div className="figma-259" data-node-id="221:651" data-name="Clip path group">
          <div className="figma-260" data-node-id="221:647" style={{ maskImage: `url("${platformsImgGroup}")` }} data-name="Group">
            <img alt="" className="figma-23" src={platformsImgGroup1} />
          </div>
        </div>
      </div>
    </div>
  );
}

function PlatformLogoSequence({ hidden = false }) {
  return (
        <div className="figma-270 platform-logo-sequence" aria-hidden={hidden || undefined} data-node-id="220:572" data-name="Infinite Scrolling Track → Track Sequence 1">
          <div className="figma-271" data-node-id="220:573" data-name="Zoom">
            <AkarIconsZoomFill className="figma-272" />
            <div className="figma-19" data-node-id="220:577" data-name="Container">
              <Fa7BrandsZoom className="figma-273" />
            </div>
          </div>
          <div className="figma-271" data-node-id="220:579" data-name="Google Meet">
            <div className="figma-274" data-node-id="220:580" data-name="Container">
              <SelfhstGoogleMeet className="figma-272" />
            </div>
            <div className="figma-19" data-node-id="220:587" data-name="Container">
              <div className="figma-275" data-node-id="220:588">
                <p className="figma-276">Google Meet</p>
              </div>
            </div>
          </div>
          <div className="figma-271" data-node-id="220:589" data-name="Microsoft Teams">
            <div className="figma-277" data-node-id="220:590" data-name="Background">
              <LogosMicrosoftTeams className="figma-278" />
            </div>
            <div className="figma-19" data-node-id="220:593" data-name="Container">
              <div className="figma-279" data-node-id="220:594">
                <p className="figma-105">Microsoft Teams</p>
              </div>
            </div>
          </div>
          <div className="figma-271" data-node-id="220:595" data-name="HackerRank">
            <div className="figma-277" data-node-id="220:596" data-name="Background">
              <CibHackerrank className="figma-272" />
            </div>
            <div className="figma-19" data-node-id="220:599" data-name="Container">
              <div className="figma-280" data-node-id="220:600">
                <p className="figma-276">HackerRank</p>
              </div>
            </div>
          </div>
          <div className="figma-281" data-node-id="220:601" data-name="LeetCode">
            <div className="figma-282" data-node-id="220:602" data-name="Container">
              <div className="figma-272" data-node-id="220:610" data-name="thesvg-color:leetcode">
                <img alt="" className="figma-23" src={platformsImgThesvgColorLeetcode} />
              </div>
            </div>
            <div className="figma-19" data-node-id="220:605" data-name="Container">
              <div className="figma-283" data-node-id="220:606">
                <p className="figma-276">LeetCode</p>
              </div>
            </div>
          </div>
        </div>
  );
}

function Platforms() {
  return (
    <div className="figma-261" data-node-id="220:563" data-name="Section">
      <div className="figma-76" data-node-id="220:564" data-name="Container">
        <div className="figma-262" data-node-id="220:565" data-name="Margin">
          <div className="figma-263" data-node-id="220:566" data-name="Background+Border">
            <div className="figma-264" data-node-id="220:567">
              <p className="figma-203">WORKS EVERYWHERE</p>
            </div>
          </div>
        </div>
        <div className="figma-265" data-node-id="220:568">
          <p className="figma-266">Works on every interview platform.</p>
        </div>
        <div className="figma-267" data-node-id="220:569" data-name="Margin">
          <div className="figma-268" data-node-id="220:570">
            <p className="figma-16">Zoom, Google Meet, Microsoft Teams, HackerRank, LeetCode — Intervucopilot works alongside the platforms candidates already use.</p>
          </div>
        </div>
      </div>
      <div className="figma-269 platform-marquee" data-node-id="220:571" data-name="Continuous Logo Marquee">
        <div className="platform-marquee-track">
          <PlatformLogoSequence />
          <PlatformLogoSequence hidden />
        </div>
        <div className="figma-284" data-node-id="220:607" data-name="Left Gradient Mask" />
        <div className="figma-285" data-node-id="220:608" data-name="Right Gradient Mask" />
      </div>
    </div>
  );
}

function DeviconFacebook({ className }) {
  return (
    <div className={className || "figma-657"} data-node-id="249:1737" data-name="devicon:facebook">
      <img alt="" className="figma-23" src={trustedImgDeviconFacebook} />
    </div>
  );
}

function BxlTwitter({ className }) {
  return (
    <div className={className || "figma-657"} data-node-id="249:1740" data-name="bxl:twitter">
      <img alt="" className="figma-23" src={trustedImgBxlTwitter} />
    </div>
  );
}

function DeviconLinkedin({ className }) {
  return (
    <div className={className || "figma-658"} data-node-id="248:1602" data-name="devicon:linkedin">
      <img alt="" className="figma-23" src={trustedImgDeviconLinkedin} />
    </div>
  );
}

function LogosNetflix({ className }) {
  return (
    <div className={className || "figma-659"} data-node-id="248:1522" data-name="logos:netflix">
      <div className="figma-286">
        <img alt="" className="figma-287" src={trustedImgLogosNetflix} />
      </div>
    </div>
  );
}

function LogosMeta({ className }) {
  return (
    <div className={className || "figma-660"} data-node-id="248:1544" data-name="logos:meta">
      <img alt="" className="figma-23" src={trustedImgLogosMeta} />
    </div>
  );
}

function SkillIconsMongodb({ className }) {
  return (
    <div className={className || "figma-661"} data-node-id="248:1609" data-name="skill-icons:mongodb">
      <img alt="" className="figma-23" src={trustedImgSkillIconsMongodb} />
    </div>
  );
}


function TrustedLogoSequence({ hidden = false }) {
  return (
        <div className="trusted-logo-sequence" aria-hidden={hidden || undefined}>
        <div className="figma-289" data-node-id="249:1614" data-name="Google">
          <div className="figma-272" data-node-id="249:1615" data-name="SVG">
            <img alt="" className="figma-23" src={trustedImgSvg} />
          </div>
          <div className="figma-19" data-node-id="249:1620" data-name="Container">
            <div className="figma-290" data-node-id="249:1621">
              <p className="figma-291">Google</p>
            </div>
          </div>
        </div>
        <div className="figma-292" data-node-id="249:1622" data-name="Microsoft">
          <div className="figma-293" data-node-id="249:1623" data-name="Container">
            <div className="figma-294" data-node-id="249:1624" data-name="Background" />
            <div className="figma-295" data-node-id="249:1625" data-name="Background" />
            <div className="figma-296" data-node-id="249:1626" data-name="Background" />
            <div className="figma-297" data-node-id="249:1627" data-name="Background" />
          </div>
          <div className="figma-19" data-node-id="249:1628" data-name="Container">
            <div className="figma-298" data-node-id="249:1629">
              <p className="figma-276">Microsoft</p>
            </div>
          </div>
        </div>
        <div className="figma-289" data-node-id="249:1630" data-name="MongoDB">
          <div className="figma-299" data-node-id="249:1631" data-name="SVG">
            <SkillIconsMongodb className="figma-300" />
          </div>
          <div className="figma-19" data-node-id="249:1633" data-name="Container">
            <div className="figma-301" data-node-id="249:1634">
              <p className="figma-105">MongoDB</p>
            </div>
          </div>
        </div>
        <div className="figma-302" data-node-id="249:1635" data-name="Meta">
          <div className="figma-19" data-node-id="249:1636" data-name="Container">
            <LogosMeta className="figma-303" />
          </div>
        </div>
        <div className="figma-304" data-node-id="249:1638" data-name="Netflix">
          <div className="figma-19" data-node-id="249:1639" data-name="Container">
            <LogosNetflix className="figma-305" />
          </div>
        </div>
        <div className="figma-306" data-node-id="249:1649" data-name="LinkedIn">
          <div className="figma-307" data-node-id="249:1650" data-name="Background">
            <DeviconLinkedin className="figma-308" />
          </div>
          <div className="figma-19" data-node-id="249:1652" data-name="Container">
            <div className="figma-298" data-node-id="249:1653">
              <p className="figma-276">LinkedIn</p>
            </div>
          </div>
        </div>
        <div className="figma-306" data-node-id="249:1654" data-name="PayPal">
          <div className="figma-19" data-node-id="249:1655" data-name="Container">
            <div className="figma-309" data-node-id="249:1656">
              <p className="figma-291">Pay</p>
            </div>
          </div>
          <div className="figma-19" data-node-id="249:1657" data-name="Container">
            <div className="figma-310" data-node-id="249:1658">
              <p className="figma-291">Pal</p>
            </div>
          </div>
        </div>
        <div className="figma-304" data-node-id="249:1659" data-name="IBM">
          <div className="figma-19" data-node-id="249:1660" data-name="Container">
            <div className="figma-311" data-node-id="249:1661">
              <p className="figma-312">IBM</p>
            </div>
          </div>
        </div>
        <div className="figma-304" data-node-id="249:1728" data-name="twitter">
          <div className="figma-19" data-node-id="249:1729" data-name="Container">
            <BxlTwitter className="figma-102" />
          </div>
        </div>
        <div className="figma-304" data-node-id="249:1731" data-name="Facebook">
          <div className="figma-19" data-node-id="249:1732" data-name="Container">
            <DeviconFacebook className="figma-102" />
          </div>
        </div>
        <div className="figma-289" data-node-id="253:1866" data-name="Google">
          <div className="figma-272" data-node-id="253:1867" data-name="SVG">
            <img alt="" className="figma-23" src={trustedImgSvg} />
          </div>
          <div className="figma-19" data-node-id="253:1872" data-name="Container">
            <div className="figma-290" data-node-id="253:1873">
              <p className="figma-291">Google</p>
            </div>
          </div>
        </div>
        <div className="figma-292" data-node-id="253:1874" data-name="Microsoft">
          <div className="figma-293" data-node-id="253:1875" data-name="Container">
            <div className="figma-294" data-node-id="253:1876" data-name="Background" />
            <div className="figma-295" data-node-id="253:1877" data-name="Background" />
            <div className="figma-296" data-node-id="253:1878" data-name="Background" />
            <div className="figma-297" data-node-id="253:1879" data-name="Background" />
          </div>
          <div className="figma-19" data-node-id="253:1880" data-name="Container">
            <div className="figma-298" data-node-id="253:1881">
              <p className="figma-276">Microsoft</p>
            </div>
          </div>
        </div>
        <div className="figma-289" data-node-id="253:1882" data-name="MongoDB">
          <div className="figma-299" data-node-id="253:1883" data-name="SVG">
            <SkillIconsMongodb className="figma-300" />
          </div>
          <div className="figma-19" data-node-id="253:1885" data-name="Container">
            <div className="figma-301" data-node-id="253:1886">
              <p className="figma-105">MongoDB</p>
            </div>
          </div>
        </div>
        <div className="figma-302" data-node-id="253:1887" data-name="Meta">
          <div className="figma-19" data-node-id="253:1888" data-name="Container">
            <LogosMeta className="figma-303" />
          </div>
        </div>
        <div className="figma-304" data-node-id="253:1890" data-name="Netflix">
          <div className="figma-19" data-node-id="253:1891" data-name="Container">
            <LogosNetflix className="figma-305" />
          </div>
        </div>
        <div className="figma-306" data-node-id="253:1893" data-name="LinkedIn">
          <div className="figma-307" data-node-id="253:1894" data-name="Background">
            <DeviconLinkedin className="figma-308" />
          </div>
          <div className="figma-19" data-node-id="253:1896" data-name="Container">
            <div className="figma-298" data-node-id="253:1897">
              <p className="figma-276">LinkedIn</p>
            </div>
          </div>
        </div>
        <div className="figma-306" data-node-id="253:1898" data-name="PayPal">
          <div className="figma-19" data-node-id="253:1899" data-name="Container">
            <div className="figma-309" data-node-id="253:1900">
              <p className="figma-291">Pay</p>
            </div>
          </div>
          <div className="figma-19" data-node-id="253:1901" data-name="Container">
            <div className="figma-310" data-node-id="253:1902">
              <p className="figma-291">Pal</p>
            </div>
          </div>
        </div>
        <div className="figma-304" data-node-id="253:1903" data-name="IBM">
          <div className="figma-19" data-node-id="253:1904" data-name="Container">
            <div className="figma-311" data-node-id="253:1905">
              <p className="figma-312">IBM</p>
            </div>
          </div>
        </div>
        <div className="figma-304" data-node-id="253:1906" data-name="twitter">
          <div className="figma-19" data-node-id="253:1907" data-name="Container">
            <BxlTwitter className="figma-102" />
          </div>
        </div>
        <div className="figma-304" data-node-id="253:1909" data-name="Facebook">
          <div className="figma-19" data-node-id="253:1910" data-name="Container">
            <DeviconFacebook className="figma-102" />
          </div>
        </div>
        </div>
  );
}

function EndlessScrollbar({ className }) {
  return (
    <div className={`${className || "figma-662"} trusted-marquee`} data-node-id="253:2079">
      <div className="figma-288 trusted-marquee-track" data-node-id="249:1613" data-name="Horizontal Clean Credibility Row">
        <TrustedLogoSequence />
        <TrustedLogoSequence hidden />
      </div>
    </div>
  );
}

function Trusted() {
  return (
    <div className="figma-313" data-node-id="221:722" data-name="Section">
      <div className="figma-74" data-node-id="221:723" data-name="Container">
        <div className="figma-75" data-node-id="221:724" data-name="Margin">
          <div className="figma-76" data-node-id="221:725" data-name="Container">
            <div className="figma-314" data-node-id="221:726">
              <p className="figma-203">TRUSTED BY CANDIDATES AT</p>
            </div>
          </div>
        </div>
        <div className="figma-315" data-node-id="221:727">
          <p className="figma-316">Used for 10,00,000+ interviews</p>
        </div>
      </div>
      <div className="figma-317" data-node-id="221:781" data-name="Continuous Logo Marquee">
        <EndlessScrollbar className="figma-318" />
        <div className="figma-284" data-node-id="221:808" data-name="Left Gradient Mask" />
        <div className="figma-285" data-node-id="221:809" data-name="Right Gradient Mask" />
      </div>
    </div>
  );
}

function IconParkOutlineVideoConference({ className }) {
  return (
    <div className={className || "figma-663"} data-node-id="207:562" data-name="icon-park-outline:video-conference">
      <img alt="" className="figma-23" src={productImgIconParkOutlineVideoConference} />
    </div>
  );
}

function Product() {
  return (
    <div className="figma-73" data-node-id="173:2805" data-name="Section - 5. PRODUCT SHOWCASE (DASHBOARD UI)">
      <div className="figma-76" data-node-id="173:2806" data-name="Container">
        <div className="figma-75" data-node-id="173:2807" data-name="Margin">
          <div className="figma-76" data-node-id="173:2808" data-name="Container">
            <div className="figma-77" data-node-id="173:2809">
              <p className="figma-78">UNIFIED WORKSPACE</p>
            </div>
          </div>
        </div>
        <div className="figma-319" data-node-id="173:2810" data-name="Heading 2">
          <div className="figma-79" data-node-id="173:2811">
            <p className="figma-80">One workspace for your entire interview journey.</p>
          </div>
        </div>
        <div className="figma-81" data-node-id="173:2812" data-name="Margin">
          <div className="figma-320" data-node-id="173:2813" data-name="Container">
            <div className="figma-83" data-node-id="173:2814">
              <p className="figma-84">Track candidate metrics, review indexed resumes, explore target company rubrics, and inspect simulated</p>
              <p className="figma-85">question banks.</p>
            </div>
          </div>
        </div>
      </div>
      <div className="figma-321" data-node-id="173:2815" data-name="Browser Mockup Container (Light Theme)">
        <div className="figma-322" data-node-id="173:2816" data-name="Window Titlebar">
          <div className="figma-323">
            <div className="figma-5" data-node-id="173:2817" data-name="Container">
              <div className="figma-324">
                <div className="figma-325" data-node-id="173:2818" data-name="Background" />
                <div className="figma-326" data-node-id="173:2819" data-name="Background" />
                <div className="figma-327" data-node-id="173:2820" data-name="Background" />
              </div>
            </div>
            <div className="figma-328" data-node-id="173:2821" data-name="Background+Border">
              <div className="figma-329">
                <div className="figma-330" data-node-id="173:2822" data-name="Container">
                  <img alt="" className="figma-23" src={productImgContainer} />
                </div>
                <div className="figma-5" data-node-id="173:2824" data-name="Container">
                  <div className="figma-6">
                    <div className="figma-331" data-node-id="173:2825">
                      <p className="figma-78">app.intervu.ai/workspace/sessions/stripe-staff-round</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="figma-332" data-node-id="173:2826" data-name="Container">
              <img alt="" className="figma-23" src={productImgContainer1} />
            </div>
          </div>
        </div>
        <div className="figma-333" data-node-id="173:2828" data-name="Inner Cockpit Dashboard Mockup">
          <div className="figma-334">
            <div className="figma-335" data-node-id="173:2829" data-name="Sidebar Navigation">
              <div className="figma-99" data-node-id="173:2830" data-name="Container">
                <div className="figma-336">
                  <div className="figma-337" data-node-id="173:2831" data-name="User Status">
                    <div className="figma-338" data-node-id="173:2832" data-name="Background+Border">
                      <div className="figma-339">
                        <div className="figma-340" data-node-id="173:2833">
                          <p className="figma-341">JD</p>
                        </div>
                      </div>
                    </div>
                    <div className="figma-5" data-node-id="173:2834" data-name="Container">
                      <div className="figma-6">
                        <div className="figma-46" data-node-id="173:2835" data-name="Container">
                          <div className="figma-342" data-node-id="173:2836">
                            <p className="figma-341">Jane Doe</p>
                          </div>
                        </div>
                        <div className="figma-46" data-node-id="173:2837" data-name="Container">
                          <div className="figma-343" data-node-id="173:2838">
                            <p className="figma-8">Senior Backend Candidate</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-344" data-node-id="173:2839" data-name="Nav Links">
                    <div className="figma-345" data-node-id="173:2840" data-name="Link">
                      <div className="figma-346" data-node-id="173:2841" data-name="Container">
                        <img alt="" className="figma-23" src={productImgContainer2} />
                      </div>
                      <div className="figma-5" data-node-id="173:2843" data-name="Container">
                        <div className="figma-6">
                          <div className="figma-232" data-node-id="173:2844">
                            <p className="figma-341">Active Workspace</p>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="figma-347" data-node-id="173:2845" data-name="Link">
                      <div className="figma-348" data-node-id="173:2846" data-name="Container">
                        <img alt="" className="figma-23" src={productImgContainer3} />
                      </div>
                      <div className="figma-19" data-node-id="173:2848" data-name="Container">
                        <div className="figma-349" data-node-id="173:2849">
                          <p className="figma-341">Resume Knowledge</p>
                        </div>
                      </div>
                    </div>
                    <div className="figma-347" data-node-id="173:2850" data-name="Link">
                      <div className="figma-346" data-node-id="173:2851" data-name="Container">
                        <img alt="" className="figma-23" src={productImgContainer4} />
                      </div>
                      <div className="figma-19" data-node-id="173:2853" data-name="Container">
                        <div className="figma-349" data-node-id="173:2854">
                          <p className="figma-341">Target Rubrics</p>
                        </div>
                      </div>
                    </div>
                    <div className="figma-347" data-node-id="173:2855" data-name="Link">
                      <div className="figma-350" data-node-id="173:2856" data-name="Container">
                        <img alt="" className="figma-23" src={productImgContainer5} />
                      </div>
                      <div className="figma-19" data-node-id="173:2858" data-name="Container">
                        <div className="figma-349" data-node-id="173:2859">
                          <p className="figma-341">Practice Arena</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="figma-99" data-node-id="173:2860" data-name="Readiness Pill Widget:margin">
                <div className="figma-108">
                  <div className="figma-351" data-node-id="173:2861" data-name="Readiness Pill Widget">
                    <div className="figma-99" data-node-id="173:2862" data-name="Container">
                      <div className="figma-131">
                        <div className="figma-19" data-node-id="173:2863" data-name="Container">
                          <div className="figma-352" data-node-id="173:2864">
                            <p className="figma-45">READINESS SCORE</p>
                          </div>
                        </div>
                        <div className="figma-19" data-node-id="173:2865" data-name="Container">
                          <div className="figma-353" data-node-id="173:2866">
                            <p className="figma-30">92%</p>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="figma-354" data-node-id="173:2867" data-name="Background">
                      <div className="figma-355">
                        <div className="figma-356" data-node-id="173:2868" data-name="Background" />
                      </div>
                    </div>
                    <div className="figma-99" data-node-id="173:2869" data-name="Container">
                      <div className="figma-6">
                        <div className="figma-49" data-node-id="173:2870">
                          <p className="figma-8">{`Resume & Desktop sync verified`}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="figma-357" data-node-id="173:2871" data-name="Main Dashboard Viewport">
              <div className="figma-358" data-node-id="173:2872" data-name="Top Telemetry Cards">
                <div className="figma-359" data-node-id="173:2873" data-name="Background+Border">
                  <div className="figma-5" data-node-id="207:549">
                    <div className="figma-360">
                      <div className="figma-361" data-node-id="207:581">
                        <div className="figma-362" data-node-id="207:586" data-name="boxicons:target">
                          <img alt="" className="figma-23" src={productImgBoxiconsTarget} />
                        </div>
                      </div>
                      <div className="figma-363" data-node-id="173:2874">
                        <p className="figma-45">ACTIVE TARGET</p>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="173:2875" data-name="Container">
                    <div className="figma-364">
                      <div className="figma-365" data-node-id="173:2876">
                        <p className="figma-105">Stripe Inc.</p>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="173:2877" data-name="Container">
                    <div className="figma-6">
                      <div className="figma-366" data-node-id="173:2878">
                        <p className="figma-78">Staff Infrastructure • Band L6</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-359" data-node-id="173:2879" data-name="Background+Border">
                  <div className="figma-5" data-node-id="207:554">
                    <div className="figma-360">
                      <div className="figma-367" data-node-id="207:576">
                        <div className="figma-362" data-node-id="207:577" data-name="basil:document-outline">
                          <img alt="" className="figma-23" src={productImgBasilDocumentOutline} />
                        </div>
                      </div>
                      <div className="figma-363" data-node-id="173:2880">
                        <p className="figma-45">INDEXED SOURCES</p>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="173:2881" data-name="Container">
                    <div className="figma-364">
                      <div className="figma-365" data-node-id="173:2882">
                        <p className="figma-105">3 Documents</p>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="173:2883" data-name="Container">
                    <div className="figma-6">
                      <div className="figma-368" data-node-id="173:2884">
                        <p className="figma-78">Resume • GitHub repo • Patents</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-359" data-node-id="173:2885" data-name="Background+Border">
                  <div className="figma-5" data-node-id="207:563">
                    <div className="figma-324">
                      <div className="figma-369" data-node-id="207:559">
                        <IconParkOutlineVideoConference className="figma-22" />
                      </div>
                      <div className="figma-363" data-node-id="173:2886">
                        <p className="figma-45">HUD SESSION</p>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="173:2887" data-name="Container">
                    <div className="figma-190">
                      <div className="figma-19" data-node-id="173:2889" data-name="Container">
                        <div className="figma-370" data-node-id="173:2890">
                          <p className="figma-105">Standby</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="figma-99" data-node-id="173:2891" data-name="Container">
                    <div className="figma-6">
                      <div className="figma-371" data-node-id="173:2892">
                        <p className="figma-78">Audio daemon connected</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="figma-372" data-node-id="173:2893" data-name="Active Session Debrief Panel">
                <div className="figma-373" data-node-id="173:2894" data-name="HorizontalBorder">
                  <div className="figma-374">
                    <div className="figma-5" data-node-id="173:2895" data-name="Paragraph">
                      <div className="figma-375">
                        <div className="figma-376" data-node-id="173:2896">
                          <p className="figma-45">LATEST SESSION INTELLIGENCE</p>
                        </div>
                        <div className="figma-377" data-node-id="173:2897">
                          <p className="figma-105">System Architecture Round • 38 min</p>
                        </div>
                      </div>
                    </div>
                    <div className="figma-5" data-node-id="173:2898" data-name="Container">
                      <div className="figma-324">
                        <div className="figma-378" data-node-id="173:2899" data-name="Background+Border">
                          <div className="figma-379" data-node-id="173:2900">
                            <p className="figma-78">14 Questions Analyzed</p>
                          </div>
                        </div>
                        <div className="figma-380" data-node-id="173:2901" data-name="Background">
                          <div className="figma-331" data-node-id="173:2902">
                            <p className="figma-78">3 Strengths Mapped</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-99" data-node-id="173:2903" data-name="Visual Performance Metrics">
                  <div className="figma-381">
                    <div className="figma-382" data-node-id="173:2904" data-name="Background+Border">
                      <div className="figma-99" data-node-id="173:2905" data-name="Container">
                        <div className="figma-131">
                          <div className="figma-19" data-node-id="173:2906" data-name="Container">
                            <div className="figma-342" data-node-id="173:2907">
                              <p className="figma-341">Technical Specificity</p>
                            </div>
                          </div>
                          <div className="figma-19" data-node-id="173:2908" data-name="Container">
                            <div className="figma-353" data-node-id="173:2909">
                              <p className="figma-30">96%</p>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="figma-383" data-node-id="173:2910" data-name="Background">
                        <div className="figma-355">
                          <div className="figma-384" data-node-id="173:2911" data-name="Background" />
                        </div>
                      </div>
                      <div className="figma-99" data-node-id="173:2912" data-name="Margin">
                        <div className="figma-385">
                          <div className="figma-43" data-node-id="173:2913" data-name="Container">
                            <div className="figma-386" data-node-id="173:2914">
                              <p className="figma-387">Strong quantification of cache eviction latency and consensus</p>
                              <p className="figma-78">protocol trade-offs.</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="figma-382" data-node-id="173:2915" data-name="Background+Border">
                      <div className="figma-99" data-node-id="173:2916" data-name="Container">
                        <div className="figma-131">
                          <div className="figma-19" data-node-id="173:2917" data-name="Container">
                            <div className="figma-342" data-node-id="173:2918">
                              <p className="figma-341">Role Rubric Alignment</p>
                            </div>
                          </div>
                          <div className="figma-19" data-node-id="173:2919" data-name="Container">
                            <div className="figma-388" data-node-id="173:2920">
                              <p className="figma-30">88%</p>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="figma-383" data-node-id="173:2921" data-name="Background">
                        <div className="figma-355">
                          <div className="figma-389" data-node-id="173:2922" data-name="Background" />
                        </div>
                      </div>
                      <div className="figma-99" data-node-id="173:2923" data-name="Margin">
                        <div className="figma-385">
                          <div className="figma-43" data-node-id="173:2924" data-name="Container">
                            <div className="figma-386" data-node-id="173:2925">
                              <p className="figma-387">Could further emphasize cross-functional stakeholder</p>
                              <p className="figma-78">management in final system choices.</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const preparationArtwork = import.meta.glob('../assets/landing/prep-*.svg', { eager: true, query: '?url', import: 'default' })
const preparationCards = [
  {
    "number": "01",
    "title": "Upload your resume",
    "body": "Drop in your PDF or LinkedIn export. Intervucopilot constructs an indexed semantic graph of every role, metric, and tech stack milestone.",
    "status": "Automatic parsing • PDF, DOCX, TXT"
  },
  {
    "number": "02",
    "title": "Set your job target",
    "body": "Paste the job description or enter target title and company. The engine maps key hiring rubrics and anticipated line-of-questioning.",
    "status": "Role rubric alignment calibrated"
  },
  {
    "number": "03",
    "title": "Connect desktop app",
    "body": "Launch our whisper-light desktop HUD. It pairs natively with your audio input/output devices with zero conference software integration needed.",
    "status": "macOS • Windows native clients"
  },
  {
    "number": "04",
    "title": "Capture live questions",
    "body": "As the interviewer speaks, the HUD isolates the core question prompt and identifies underlying architectural or behavioral intent.",
    "status": "Zero audio transmission latency"
  },
  {
    "number": "05",
    "title": "Receive AI guidance",
    "body": "Glance at structured STAR bullet prompts pulled directly from your indexed projects, giving you rapid recall without script reading.",
    "status": "Non-intrusive cue cards"
  },
  {
    "number": "06",
    "title": "Review and iterate",
    "body": "Review detailed AI debriefs, question breakdowns, and simulated follow-ups to make each round stronger than the last.",
    "status": "Continuous interview growth"
  }
]
const preparationFrames = [
  {
    "id": "227:21508",
    "height": 353.89910888671875,
    "cards": [
      {
        "slot": 0,
        "nodeId": "224:2853",
        "number": "06",
        "width": 688,
        "height": 340,
        "copy": {
          "x": 40.9140625,
          "y": 48,
          "width": 240,
          "height": 244
        },
        "art": {
          "id": "224:4588",
          "name": "documents/cuate",
          "x": 304.9140625,
          "y": 47.999916076660156,
          "width": 342.171875,
          "height": 244.0001678466797,
          "asset": "prep-06-left-1.svg"
        },
        "icon": {
          "id": "224:3029",
          "width": 13.333333015441895,
          "height": 8,
          "asset": "prep-06-status-left-1.svg"
        }
      },
      {
        "slot": 1,
        "nodeId": "222:1785",
        "number": "01",
        "width": 738,
        "height": 353.89910888671875,
        "copy": {
          "x": 39.27870178222656,
          "y": 52.449554443359375,
          "width": 307,
          "height": 249
        },
        "art": {
          "id": "224:3318",
          "name": "documents/amico",
          "x": 403.2786865234375,
          "y": 59.20726776123047,
          "width": 295.4425964355469,
          "height": 235.4845733642578,
          "asset": "prep-01-active-1.svg"
        },
        "icon": {
          "id": "222:1796",
          "width": 12,
          "height": 15,
          "asset": "prep-01-status.svg"
        }
      },
      {
        "slot": 2,
        "nodeId": "222:1954",
        "number": "02",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 51.676025390625,
          "y": 51.5,
          "width": 285,
          "height": 222
        },
        "art": {
          "id": "222:2223",
          "name": "mobile-login/amico",
          "x": 360.676025390625,
          "y": 34.49989318847656,
          "width": 275.64794921875,
          "height": 256.0002136230469,
          "asset": "prep-02-right-1.svg"
        },
        "icon": {
          "id": "227:30192",
          "width": 9.333333015441895,
          "height": 13.333333015441895,
          "asset": "prep-02-status-right-1.svg"
        }
      }
    ]
  },
  {
    "id": "227:21509",
    "height": 354,
    "cards": [
      {
        "slot": 0,
        "nodeId": "225:13372",
        "number": "01",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 30.778701782226562,
          "y": 51.5,
          "width": 307,
          "height": 222
        },
        "art": {
          "id": "225:13387",
          "name": "documents/amico",
          "x": 361.7786865234375,
          "y": 44.75775146484375,
          "width": 295.4425964355469,
          "height": 235.4844970703125,
          "asset": "prep-01-left-2.svg"
        },
        "icon": {
          "id": "225:13384",
          "width": 10.666666984558105,
          "height": 13.333333015441895,
          "asset": "prep-01-status-left-2.svg"
        }
      },
      {
        "slot": 1,
        "nodeId": "225:13494",
        "number": "02",
        "width": 738,
        "height": 354,
        "copy": {
          "x": 43.52490234375,
          "y": 52.5,
          "width": 285,
          "height": 249
        },
        "art": {
          "id": "225:13509",
          "name": "mobile-login/amico",
          "x": 386.52490234375,
          "y": 33.99981689453125,
          "width": 307.9501953125,
          "height": 286.0003662109375,
          "asset": "prep-02-active-2.svg"
        },
        "icon": {
          "id": "227:30186",
          "width": 10,
          "height": 15,
          "asset": "prep-02-status.svg"
        }
      },
      {
        "slot": 2,
        "nodeId": "225:13613",
        "number": "03",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 24.7216796875,
          "y": 40.5,
          "width": 307,
          "height": 244
        },
        "art": {
          "id": "225:13628",
          "name": "devices/rafiki",
          "x": 355.7216796875,
          "y": 26.444778442382812,
          "width": 307.556640625,
          "height": 272.1104431152344,
          "asset": "prep-03-right-2.svg"
        },
        "icon": {
          "id": "225:13625",
          "width": 16,
          "height": 11.333333015441895,
          "asset": "prep-03-status-right-2.svg"
        }
      }
    ]
  },
  {
    "id": "227:21510",
    "height": 354,
    "cards": [
      {
        "slot": 0,
        "nodeId": "225:14850",
        "number": "02",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 51.676025390625,
          "y": 51.5,
          "width": 285,
          "height": 222
        },
        "art": {
          "id": "225:14865",
          "name": "mobile-login/amico",
          "x": 360.676025390625,
          "y": 34.49989318847656,
          "width": 275.64794921875,
          "height": 256.0002136230469,
          "asset": "prep-02-left-3.svg"
        },
        "icon": {
          "id": "227:30178",
          "width": 9.333333015441895,
          "height": 13.333333015441895,
          "asset": "prep-02-status-left-3.svg"
        }
      },
      {
        "slot": 1,
        "nodeId": "225:14969",
        "number": "03",
        "width": 738,
        "height": 354,
        "copy": {
          "x": 38.3515625,
          "y": 52.5,
          "width": 307,
          "height": 249
        },
        "art": {
          "id": "225:14984",
          "name": "devices/rafiki",
          "x": 369.3515625,
          "y": 46.4462890625,
          "width": 330.296875,
          "height": 261.1073913574219,
          "asset": "prep-03-active-3.svg"
        },
        "icon": {
          "id": "225:14981",
          "width": 18,
          "height": 13,
          "asset": "prep-03-status.svg"
        }
      },
      {
        "slot": 2,
        "nodeId": "225:15197",
        "number": "04",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 30.2276611328125,
          "y": 40.5,
          "width": 264,
          "height": 244
        },
        "art": {
          "id": "225:15212",
          "name": "search/cuate",
          "x": 318.2276611328125,
          "y": 45.499725341796875,
          "width": 339.544677734375,
          "height": 234.00054931640625,
          "asset": "prep-04-right-3.svg"
        },
        "icon": {
          "id": "225:15209",
          "width": 14.666666984558105,
          "height": 12.633333206176758,
          "asset": "prep-04-status-right-3.svg"
        }
      }
    ]
  },
  {
    "id": "227:21511",
    "height": 354,
    "cards": [
      {
        "slot": 0,
        "nodeId": "235:1034",
        "number": "03",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 24.7216796875,
          "y": 40.5,
          "width": 307,
          "height": 244
        },
        "art": {
          "id": "235:1049",
          "name": "devices/rafiki",
          "x": 355.7216796875,
          "y": 26.444778442382812,
          "width": 307.556640625,
          "height": 272.1104431152344,
          "asset": "prep-03-left-4.svg"
        },
        "icon": {
          "id": "235:1046",
          "width": 16,
          "height": 11.333333015441895,
          "asset": "prep-03-status-left-4.svg"
        }
      },
      {
        "slot": 1,
        "nodeId": "225:16553",
        "number": "04",
        "width": 738,
        "height": 354,
        "copy": {
          "x": 40.578125,
          "y": 52.5,
          "width": 264,
          "height": 249
        },
        "art": {
          "id": "225:16568",
          "name": "search/cuate",
          "x": 328.578125,
          "y": 49.90355682373047,
          "width": 368.84375,
          "height": 254.19288635253906,
          "asset": "prep-04-active-4.svg"
        },
        "icon": {
          "id": "225:16565",
          "width": 17,
          "height": 15,
          "asset": "prep-04-status.svg"
        }
      },
      {
        "slot": 2,
        "nodeId": "225:16848",
        "number": "05",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 41,
          "y": 51.5,
          "width": 307,
          "height": 222
        },
        "art": {
          "id": "225:16863",
          "name": "at-work/cuate",
          "x": 372,
          "y": 33.4522705078125,
          "width": 275,
          "height": 258.095458984375,
          "asset": "prep-05-right-4.svg"
        },
        "icon": {
          "id": "225:16860",
          "width": 14.666666984558105,
          "height": 14.666666984558105,
          "asset": "prep-05-status-right-4.svg"
        }
      }
    ]
  },
  {
    "id": "227:21512",
    "height": 354,
    "cards": [
      {
        "slot": 0,
        "nodeId": "225:17909",
        "number": "04",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 21,
          "y": 40.5,
          "width": 264,
          "height": 244
        },
        "art": {
          "id": "225:17924",
          "name": "search/cuate",
          "x": 309,
          "y": 39.14015197753906,
          "width": 358,
          "height": 246.71969604492188,
          "asset": "prep-04-left-5.svg"
        },
        "icon": {
          "id": "225:17921",
          "width": 14.666666984558105,
          "height": 12.633333206176758,
          "asset": "prep-04-status-left-5.svg"
        }
      },
      {
        "slot": 1,
        "nodeId": "225:18204",
        "number": "05",
        "width": 738,
        "height": 354,
        "copy": {
          "x": 40.47895812988281,
          "y": 52.5,
          "width": 307,
          "height": 249
        },
        "art": {
          "id": "225:18219",
          "name": "at-work/cuate",
          "x": 371.47894287109375,
          "y": 24.000076293945312,
          "width": 326.0420837402344,
          "height": 305.9998474121094,
          "asset": "prep-05-active-5.svg"
        },
        "icon": {
          "id": "225:18216",
          "width": 16,
          "height": 16,
          "asset": "prep-05-status.svg"
        }
      },
      {
        "slot": 2,
        "nodeId": "225:18554",
        "number": "06",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 40.9140625,
          "y": 40.5,
          "width": 240,
          "height": 244
        },
        "art": {
          "id": "225:18569",
          "name": "documents/cuate",
          "x": 304.9140625,
          "y": 40.499916076660156,
          "width": 342.171875,
          "height": 244.0001678466797,
          "asset": "prep-06-right-5.svg"
        },
        "icon": {
          "id": "225:18566",
          "width": 13.333333015441895,
          "height": 8,
          "asset": "prep-06-status-right-5.svg"
        }
      }
    ]
  },
  {
    "id": "227:21513",
    "height": 354,
    "cards": [
      {
        "slot": 0,
        "nodeId": "225:19560",
        "number": "05",
        "width": 688,
        "height": 324,
        "copy": {
          "x": 41,
          "y": 51,
          "width": 307,
          "height": 222
        },
        "art": {
          "id": "225:19575",
          "name": "at-work/cuate",
          "x": 372,
          "y": 32.9522705078125,
          "width": 275,
          "height": 258.095458984375,
          "asset": "prep-05-left-6.svg"
        },
        "icon": {
          "id": "225:19572",
          "width": 14.666666984558105,
          "height": 14.666666984558105,
          "asset": "prep-05-status-left-6.svg"
        }
      },
      {
        "slot": 1,
        "nodeId": "225:19910",
        "number": "06",
        "width": 738,
        "height": 354,
        "copy": {
          "x": 40.50019836425781,
          "y": 41,
          "width": 240,
          "height": 272
        },
        "art": {
          "id": "225:19925",
          "name": "documents/cuate",
          "x": 323.50018310546875,
          "y": 43.65153503417969,
          "width": 373.9996032714844,
          "height": 266.6969299316406,
          "asset": "prep-06-active-6.svg"
        },
        "icon": {
          "id": "225:19922",
          "width": 17,
          "height": 10,
          "asset": "prep-06-status.svg"
        }
      },
      {
        "slot": 2,
        "nodeId": "225:18796",
        "number": "01",
        "width": 688,
        "height": 325,
        "copy": {
          "x": 25,
          "y": 25,
          "width": 307,
          "height": 222
        },
        "art": {
          "id": "225:18811",
          "name": "documents/amico",
          "x": 356,
          "y": 25,
          "width": 295.4425964355469,
          "height": 235.4840850830078,
          "asset": "prep-01-right-6.svg"
        },
        "icon": {
          "id": "225:18808",
          "width": 10.666666984558105,
          "height": 13.333333015441895,
          "asset": "prep-01-status-right-6.svg"
        }
      }
    ]
  }
]

function Slider({ className }) {
  const [activeIndex, setActiveIndex] = useState(0)
  const frame = preparationFrames[activeIndex]
  const move = direction => setActiveIndex(index => (index + direction + preparationCards.length) % preparationCards.length)

  return (
    <div className={`${className || ''} preparation-slider`} data-node-id="227:21514"
      data-active-card={preparationCards[activeIndex].number}
      role="region" aria-roledescription="carousel" aria-label="Preparation steps"
      style={{ '--slider-height': `${frame.height}px` }}>
      {frame.cards.map((geometry, slot) => {
        const card = preparationCards[Number(geometry.number) - 1]
        const active = slot === 1
        return (
          <div key={slot} className={`preparation-slot${active ? ' preparation-slot--active' : ''}`}
            style={{ '--card-width': `${geometry.width}px`, '--card-height': `${geometry.height}px` }}>
            <article className={`preparation-card${active ? ' preparation-card--active' : ''}`}
              data-node-id={geometry.nodeId} data-card-number={card.number}
              aria-label={`Step ${card.number}: ${card.title}`} aria-current={active ? 'step' : undefined}>
              <div className="preparation-copy" style={{
                '--copy-left': `${geometry.copy.x}px`, '--copy-top': `${geometry.copy.y}px`,
                '--copy-width': `${geometry.copy.width}px`, '--copy-height': `${geometry.copy.height}px`,
              }}>
                <span className="preparation-number">{card.number}</span>
                <h3>{card.title}</h3>
                <p>{card.body}</p>
                <div className="preparation-status">
                  <img src={preparationArtwork[`../assets/landing/${geometry.icon.asset}`]} alt=""
                    style={{ width: geometry.icon.width, height: geometry.icon.height }} />
                  <span>{card.status}</span>
                </div>
              </div>
              <div className="preparation-art" data-node-id={geometry.art.id} style={{
                '--art-left': `${geometry.art.x}px`, '--art-top': `${geometry.art.y}px`,
                '--art-width': `${geometry.art.width}px`, '--art-height': `${geometry.art.height}px`,
              }}>
                <img src={preparationArtwork[`../assets/landing/${geometry.art.asset}`]} alt="" />
              </div>
            </article>
          </div>
        )
      })}
      <button type="button" className="preparation-arrow preparation-arrow--previous"
        aria-label="Previous preparation step" onClick={() => move(-1)}>
        <img src={preparationImgDashiconsArrowLeftAlt2} alt="" />
      </button>
      <button type="button" className="preparation-arrow preparation-arrow--next"
        aria-label="Next preparation step" onClick={() => move(1)}>
        <img src={preparationImgDashiconsArrowRightAlt2} alt="" />
      </button>
      <span className="preparation-announcement" aria-live="polite" aria-atomic="true">
        Step {preparationCards[activeIndex].number} of 6: {preparationCards[activeIndex].title}
      </span>
    </div>
  )
}

function Preparation() {
  return (
    <div className="figma-418" data-node-id="235:2008">
      <div className="figma-76" data-node-id="235:2011" data-name="Container">
        <div className="figma-75" data-node-id="235:2012" data-name="Margin">
          <div className="figma-76" data-node-id="235:2013" data-name="Container">
            <div className="figma-77" data-node-id="235:2014">
              <p className="figma-78">SEAMLESS PREPARATION WORKFLOW</p>
            </div>
          </div>
        </div>
        <div className="figma-419" data-node-id="235:2015" data-name="Heading 2">
          <div className="figma-79" data-node-id="235:2016">
            <p className="figma-80">From preparation to reflection, in one flow.</p>
          </div>
        </div>
        <div className="figma-81" data-node-id="235:2017" data-name="Margin">
          <div className="figma-420" data-node-id="235:2018" data-name="Container">
            <div className="figma-83" data-node-id="235:2019">
              <p className="figma-85">A structured, repeatable protocol designed to build unshakable confidence in high-stakes technical and leadership interviews.</p>
            </div>
          </div>
        </div>
      </div>
      <Slider className="figma-421" />
    </div>
  );
}

function Desktop() {
  return (
    <div className="figma-422" data-node-id="173:3021" data-name="Section - 7. DESKTOP APP SECTION">
      <div className="figma-423" data-node-id="173:3022" data-name="Background+Border+Shadow">
        <div className="figma-99" data-node-id="173:3024" data-name="Container">
          <div className="figma-424">
            <div className="figma-425" data-node-id="173:3025" data-name="Container">
              <div className="figma-426" data-node-id="173:3026" data-name="Background+Border">
                <div className="figma-427" data-node-id="173:3027" data-name="Container">
                  <img alt="" className="figma-23" src={desktopImgContainer} />
                </div>
                <div className="figma-5" data-node-id="173:3029" data-name="Container">
                  <div className="figma-6">
                    <div className="figma-428" data-node-id="173:3030">
                      <p className="figma-8">DESKTOP HUD COMPANION</p>
                    </div>
                  </div>
                </div>
              </div>
              <div className="figma-429" data-node-id="173:3031" data-name="Heading 2">
                <div className="figma-430" data-node-id="173:3032">
                  <p className="figma-431">Bring Intervucopilot directly into your interview workflow.</p>
                </div>
              </div>
              <div className="figma-432" data-node-id="173:3033" data-name="Container">
                <div className="figma-433" data-node-id="173:3034">
                  <p className="figma-84">A cohesive duo: the Web Workspace handles deep resume curation, role target</p>
                  <p className="figma-84">rubrics, and longitudinal analytics. The Desktop App remains unobtrusively</p>
                  <p className="figma-85">docked during live interviews for real-time memory cues.</p>
                </div>
              </div>
              <div className="figma-434" data-node-id="173:3035" data-name="Container">
                <div className="figma-435" data-node-id="173:3036" data-name="Button">
                  <div className="figma-436" data-node-id="173:3037" data-name="Container">
                    <img alt="" className="figma-23" src={desktopImgContainer1} />
                  </div>
                  <div className="figma-76" data-node-id="173:3039" data-name="Container">
                    <div className="figma-437" data-node-id="173:3040">
                      <p className="figma-21">Download Desktop App (macOS • Windows)</p>
                    </div>
                  </div>
                </div>
                <div className="figma-438" data-node-id="173:3041" data-name="Link">
                  <div className="figma-26" data-node-id="173:3042">
                    <p className="figma-21">Learn How It Works</p>
                  </div>
                </div>
              </div>
              <div className="figma-439" data-node-id="173:3043" data-name="Container">
                <div className="figma-440" data-node-id="173:3044" data-name="Container">
                  <div className="figma-346" data-node-id="173:3045" data-name="Container">
                    <img alt="" className="figma-23" src={desktopImgContainer2} />
                  </div>
                  <div className="figma-19" data-node-id="173:3047" data-name="Container">
                    <div className="figma-29" data-node-id="173:3048">
                      <p className="figma-30">Screen-share invisible</p>
                    </div>
                  </div>
                </div>
                <div className="figma-440" data-node-id="173:3049" data-name="Container">
                  <div className="figma-346" data-node-id="173:3050" data-name="Container">
                    <img alt="" className="figma-23" src={desktopImgContainer2} />
                  </div>
                  <div className="figma-19" data-node-id="173:3052" data-name="Container">
                    <div className="figma-29" data-node-id="173:3053">
                      <p className="figma-30">Low CPU footprint</p>
                    </div>
                  </div>
                </div>
                <div className="figma-440" data-node-id="173:3054" data-name="Container">
                  <div className="figma-346" data-node-id="173:3055" data-name="Container">
                    <img alt="" className="figma-23" src={desktopImgContainer2} />
                  </div>
                  <div className="figma-19" data-node-id="173:3057" data-name="Container">
                    <div className="figma-29" data-node-id="173:3058">
                      <p className="figma-30">Universal meeting support</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="figma-441" data-node-id="173:3059" data-name="HUD Mock Graphic">
              <div className="figma-442" data-node-id="173:3060" data-name="Background+Border">
                <div className="figma-443" data-node-id="173:3061" data-name="Overlay+Shadow" />
                <div className="figma-373" data-node-id="173:3062" data-name="HorizontalBorder">
                  <div className="figma-444">
                    <div className="figma-5" data-node-id="173:3063" data-name="Container">
                      <div className="figma-324">
                        <div className="figma-4" data-node-id="173:3064" data-name="Background+Shadow" />
                        <div className="figma-19" data-node-id="173:3065" data-name="Container">
                          <div className="figma-445" data-node-id="173:3066">
                            <p>
                              <span className="figma-446">Intervu</span>
                              <span className="figma-78">{` AI HUD • ACTIVE`}</span>
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="figma-5" data-node-id="173:3067" data-name="Container">
                      <div className="figma-6">
                        <div className="figma-447" data-node-id="173:3068">
                          <p className="figma-45">MINIMAL MODE</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-448" data-node-id="173:3069" data-name="Background+Border">
                  <div className="figma-449">
                    <div className="figma-450" data-node-id="173:3070">
                      <p className="figma-45">INTERVIEWER QUESTION</p>
                    </div>
                    <div className="figma-99" data-node-id="173:3071" data-name="Container">
                      <div className="figma-6">
                        <div className="figma-451" data-node-id="173:3072">
                          <p className="figma-452">“Why choose Cassandra over Postgres for this event</p>
                          <p className="figma-341">stream?”</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="figma-448" data-node-id="173:3073" data-name="Background+Border">
                  <div className="figma-453">
                    <div className="figma-454" data-node-id="173:3074">
                      <p className="figma-45">YOUR CONTEXT BULLETS</p>
                    </div>
                    <div className="figma-99" data-node-id="173:3075" data-name="List">
                      <div className="figma-455">
                        <div className="figma-43" data-node-id="173:3076" data-name="Item">
                          <div className="figma-456" data-node-id="173:3077">
                            <p className="figma-30">• Handled 80k/sec write heavy ingestion at previous firm</p>
                          </div>
                        </div>
                        <div className="figma-43" data-node-id="173:3078" data-name="Item">
                          <div className="figma-456" data-node-id="173:3079">
                            <p className="figma-30">• Tunable consistency (QUORUM) matched our loss-tolerance</p>
                          </div>
                        </div>
                        <div className="figma-43" data-node-id="173:3080" data-name="Item">
                          <div className="figma-456" data-node-id="173:3081">
                            <p className="figma-30">{`• Postgres vacuum contention became bottleneck at >10TB`}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Privacy() {
  return (
    <div className="figma-73" data-node-id="173:3082" data-name="Section - 8. PRIVACY & CONTROL">
      <div className="figma-74" data-node-id="173:3083" data-name="Container">
        <div className="figma-75" data-node-id="173:3084" data-name="Margin">
          <div className="figma-76" data-node-id="173:3085" data-name="Container">
            <div className="figma-77" data-node-id="173:3086">
              <p className="figma-78">ENTERPRISE GRADE INTEGRITY</p>
            </div>
          </div>
        </div>
        <div className="figma-79" data-node-id="173:3087">
          <p className="figma-80">Your data. Your control.</p>
        </div>
        <div className="figma-81" data-node-id="173:3088" data-name="Margin">
          <div className="figma-76" data-node-id="173:3089" data-name="Container">
            <div className="figma-83" data-node-id="173:3090">
              <p className="figma-85">We treat your career history, candidate notes, and voice data with strict institutional privacy standards.</p>
            </div>
          </div>
        </div>
      </div>
      <div className="figma-457" data-node-id="173:3091" data-name="Container">
        <div className="figma-458" data-node-id="173:3092" data-name="Background+Border">
          <div className="figma-459" data-node-id="173:3093" data-name="Background">
            <div className="figma-460" data-node-id="173:3094" data-name="Container">
              <img alt="" className="figma-23" src={privacyImgContainer} />
            </div>
          </div>
          <div className="figma-461" data-node-id="173:3096" data-name="Heading 3">
            <div className="figma-462" data-node-id="173:3097">
              <p className="figma-105">Secure Storage</p>
            </div>
          </div>
          <div className="figma-463" data-node-id="173:3098" data-name="Container">
            <div className="figma-464" data-node-id="173:3099">
              <p className="figma-114">All resume tokens and transcripts are</p>
              <p className="figma-114">encrypted in transit via TLS 1.3 and</p>
              <p className="figma-107">at rest with AES-256 standard keys.</p>
            </div>
          </div>
        </div>
        <div className="figma-458" data-node-id="173:3100" data-name="Background+Border">
          <div className="figma-459" data-node-id="173:3101" data-name="Background">
            <div className="figma-465" data-node-id="173:3102" data-name="Container">
              <img alt="" className="figma-23" src={privacyImgContainer1} />
            </div>
          </div>
          <div className="figma-461" data-node-id="173:3104" data-name="Heading 3">
            <div className="figma-462" data-node-id="173:3105">
              <p className="figma-105">Data Controls</p>
            </div>
          </div>
          <div className="figma-463" data-node-id="173:3106" data-name="Container">
            <div className="figma-464" data-node-id="173:3107">
              <p className="figma-114">You choose whether your sessions</p>
              <p className="figma-114">are recorded, transcribed, or kept</p>
              <p className="figma-107">purely volatile in local memory.</p>
            </div>
          </div>
        </div>
        <div className="figma-466" data-node-id="173:3108" data-name="Background+Border">
          <div className="figma-467" data-node-id="173:3109" data-name="Background">
            <div className="figma-468">
              <div className="figma-469" data-node-id="173:3110" data-name="Container">
                <img alt="" className="figma-23" src={privacyImgContainer2} />
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:3112" data-name="Heading 3">
            <div className="figma-6">
              <div className="figma-104" data-node-id="173:3113">
                <p className="figma-105">Delete Anytime</p>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:3114" data-name="Container">
            <div className="figma-6">
              <div className="figma-106" data-node-id="173:3115">
                <p className="figma-114">One-click complete purge. Deleting</p>
                <p className="figma-114">your workspace immediately scrubs</p>
                <p className="figma-107">all resumes, audio snippets, and logs from our servers.</p>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-466" data-node-id="173:3116" data-name="Background+Border">
          <div className="figma-467" data-node-id="173:3117" data-name="Background">
            <div className="figma-468">
              <div className="figma-470" data-node-id="173:3118" data-name="Container">
                <img alt="" className="figma-23" src={privacyImgContainer3} />
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:3120" data-name="Heading 3">
            <div className="figma-6">
              <div className="figma-104" data-node-id="173:3121">
                <p className="figma-105">Transparent AI</p>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:3122" data-name="Container">
            <div className="figma-6">
              <div className="figma-106" data-node-id="173:3123">
                <p className="figma-114">We never train foundational AI</p>
                <p className="figma-114">models on your private interview</p>
                <p className="figma-114">responses or proprietary resume</p>
                <p className="figma-107">documentation.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Pricing() {
  return (
    <div className="figma-73" data-node-id="173:3124" data-name="Section - 9. PRICING PREVIEW">
      <div className="figma-471" data-node-id="188:500">
        <img alt="" className="figma-23" src={pricingImgRectangle1} />
      </div>
      <div className="figma-74" data-node-id="173:3125" data-name="Container">
        <div className="figma-75" data-node-id="173:3126" data-name="Margin">
          <div className="figma-76" data-node-id="173:3127" data-name="Container">
            <div className="figma-77" data-node-id="173:3128">
              <p className="figma-78">TRANSPARENT INVESTMENT</p>
            </div>
          </div>
        </div>
        <div className="figma-472" data-node-id="173:3129" data-name="Heading 2">
          <div className="figma-79" data-node-id="173:3130">
            <p className="figma-80">Choose the plan that fits your preparation.</p>
          </div>
        </div>
        <div className="figma-81" data-node-id="173:3131" data-name="Margin">
          <div className="figma-473" data-node-id="173:3132" data-name="Container">
            <div className="figma-83" data-node-id="173:3133">
              <p className="figma-85">Scale your preparation smoothly whether you are entering the job market or aiming for a tier-1 executive technical band.</p>
            </div>
          </div>
        </div>
        <div className="figma-474" data-node-id="173:3134" data-name="Billing Frequency Pill Toggle:margin">
          <div className="figma-475" data-node-id="173:3135" data-name="Billing Frequency Pill Toggle">
            <div className="figma-476" data-node-id="173:3136" data-name="Button">
              <div className="figma-477">
                <div className="figma-478" data-node-id="173:3137">
                  <p className="figma-341">Monthly</p>
                </div>
              </div>
            </div>
            <div className="figma-479" data-node-id="173:3138" data-name="Button">
              <div className="figma-480">
                <div className="figma-76" data-node-id="173:3139" data-name="Container">
                  <div className="figma-481" data-node-id="173:3140">
                    <p className="figma-341">Yearly</p>
                  </div>
                </div>
                <div className="figma-482" data-node-id="173:3141" data-name="Overlay">
                  <div className="figma-483" data-node-id="173:3142">
                    <p className="figma-45">SAVE 20%</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="figma-484" data-node-id="173:3143" data-name="4 Pricing Cards">
        <div className="figma-485" data-node-id="173:3144" data-name="Free Plan">
          <div className="figma-99" data-node-id="173:3145" data-name="Container">
            <div className="figma-486">
              <div className="figma-487" data-node-id="173:3146">
                <p className="figma-8">FREE</p>
              </div>
              <div className="figma-488" data-node-id="173:3147" data-name="Paragraph">
                <div className="figma-489" data-node-id="173:3148">
                  <p className="figma-490">$0</p>
                </div>
                <div className="figma-491" data-node-id="173:3149">
                  <p className="figma-30">/ forever</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:3150" data-name="Container">
                <div className="figma-492" data-node-id="173:3151">
                  <p className="figma-173">Explore context ingestion and practice</p>
                  <p className="figma-174">standard interview rubrics.</p>
                </div>
              </div>
              <div className="figma-493" data-node-id="173:3152" data-name="List">
                <div className="figma-211" data-node-id="173:3153" data-name="Item">
                  <div className="figma-494" data-node-id="173:3154" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer} />
                  </div>
                  <div className="figma-19" data-node-id="173:3156" data-name="Container">
                    <div className="figma-36" data-node-id="173:3157">
                      <p className="figma-30">1 Resume Indexed</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3158" data-name="Item">
                  <div className="figma-494" data-node-id="173:3159" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer} />
                  </div>
                  <div className="figma-19" data-node-id="173:3161" data-name="Container">
                    <div className="figma-36" data-node-id="173:3162">
                      <p className="figma-30">2 Live Mock Sessions</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3163" data-name="Item">
                  <div className="figma-494" data-node-id="173:3164" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer} />
                  </div>
                  <div className="figma-19" data-node-id="173:3166" data-name="Container">
                    <div className="figma-36" data-node-id="173:3167">
                      <p className="figma-30">Standard STAR Framework</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:3168" data-name="Link:margin">
            <div className="figma-495">
              <a href="/auth/signup" className="figma-496" data-node-id="173:3169" data-name="Link">
                <div className="figma-497" data-node-id="173:3170">
                  <p className="figma-341">Get Started</p>
                </div>
              </a>
            </div>
          </div>
        </div>
        <div className="figma-498" data-node-id="173:3171" data-name="Student Plan">
          <div className="figma-99" data-node-id="173:3172" data-name="Container">
            <div className="figma-486">
              <div className="figma-499" data-node-id="173:3173">
                <p className="figma-8">STUDENT</p>
              </div>
              <div className="figma-488" data-node-id="173:3174" data-name="Paragraph">
                <div className="figma-489" data-node-id="173:3175">
                  <p className="figma-490">$12</p>
                </div>
                <div className="figma-491" data-node-id="173:3176">
                  <p className="figma-30">/ mo</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:3177" data-name="Container">
                <div className="figma-492" data-node-id="173:3178">
                  <p className="figma-173">Built for new grads and campus</p>
                  <p className="figma-174">recruitment cycles.</p>
                </div>
              </div>
              <div className="figma-493" data-node-id="173:3179" data-name="List">
                <div className="figma-211" data-node-id="173:3180" data-name="Item">
                  <div className="figma-494" data-node-id="173:3181" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer1} />
                  </div>
                  <div className="figma-19" data-node-id="173:3183" data-name="Container">
                    <div className="figma-36" data-node-id="173:3184">
                      <p className="figma-30">3 Resumes Indexed</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3185" data-name="Item">
                  <div className="figma-494" data-node-id="173:3186" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer1} />
                  </div>
                  <div className="figma-19" data-node-id="173:3188" data-name="Container">
                    <div className="figma-36" data-node-id="173:3189">
                      <p className="figma-30">Unlimited Practice Arena</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3190" data-name="Item">
                  <div className="figma-494" data-node-id="173:3191" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer1} />
                  </div>
                  <div className="figma-19" data-node-id="173:3193" data-name="Container">
                    <div className="figma-36" data-node-id="173:3194">
                      <p className="figma-30">Desktop HUD Access</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:3195" data-name="Link:margin">
            <div className="figma-495">
              <div className="figma-496" data-node-id="173:3196" data-name="Link">
                <div className="figma-497" data-node-id="173:3197">
                  <p className="figma-341">Verify Student ID</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-500" data-node-id="173:3224" data-name="Pro Plan (Recommended)">
          <div className="figma-99" data-node-id="173:3225" data-name="Container">
            <div className="figma-486">
              <div className="figma-428" data-node-id="173:3226">
                <p className="figma-8">PRO CANDIDATE</p>
              </div>
              <div className="figma-488" data-node-id="173:3227" data-name="Paragraph">
                <div className="figma-501" data-node-id="173:3228">
                  <p className="figma-490">$29</p>
                </div>
                <div className="figma-491" data-node-id="173:3229">
                  <p className="figma-30">/ mo</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:3230" data-name="Container">
                <div className="figma-492" data-node-id="173:3231">
                  <p className="figma-173">Full power for active job searches</p>
                  <p className="figma-174">{`across senior & staff roles.`}</p>
                </div>
              </div>
              <div className="figma-493" data-node-id="173:3232" data-name="List">
                <div className="figma-211" data-node-id="173:3233" data-name="Item">
                  <div className="figma-494" data-node-id="173:3234" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer} />
                  </div>
                  <div className="figma-19" data-node-id="173:3236" data-name="Container">
                    <div className="figma-47" data-node-id="173:3237">
                      <p className="figma-30">{`Unlimited Resumes & Rubrics`}</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3238" data-name="Item">
                  <div className="figma-494" data-node-id="173:3239" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer} />
                  </div>
                  <div className="figma-19" data-node-id="173:3241" data-name="Container">
                    <div className="figma-47" data-node-id="173:3242">
                      <p className="figma-30">Full Desktop HUD Support</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3243" data-name="Item">
                  <div className="figma-494" data-node-id="173:3244" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer} />
                  </div>
                  <div className="figma-19" data-node-id="173:3246" data-name="Container">
                    <div className="figma-47" data-node-id="173:3247">
                      <p className="figma-30">Real-Time Context Cue Cards</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3248" data-name="Item">
                  <div className="figma-494" data-node-id="173:3249" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer} />
                  </div>
                  <div className="figma-19" data-node-id="173:3251" data-name="Container">
                    <div className="figma-47" data-node-id="173:3252">
                      <p className="figma-30">Post-Interview AI Retrospectives</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:3253" data-name="Link:margin">
            <div className="figma-495">
              <div className="figma-502" data-node-id="173:3254" data-name="Link">
                <div className="figma-478" data-node-id="173:3255">
                  <p className="figma-341">Start Pro Trial</p>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-503" data-node-id="173:3256" data-name="Background">
            <div className="figma-504">
              <div className="figma-505" data-node-id="173:3257" data-name="Overlay+Shadow" />
              <div className="figma-506" data-node-id="173:3258">
                <p className="figma-45">RECOMMENDED</p>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-507" data-node-id="173:3198" data-name="Institution Plan">
          <div className="figma-99" data-node-id="173:3199" data-name="Container">
            <div className="figma-486">
              <div className="figma-487" data-node-id="173:3200">
                <p className="figma-8">INSTITUTION</p>
              </div>
              <div className="figma-508" data-node-id="173:3201" data-name="Container">
                <div className="figma-509" data-node-id="173:3202">
                  <p className="figma-490">Custom</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:3203" data-name="Container">
                <div className="figma-492" data-node-id="173:3204">
                  <p className="figma-173">For bootcamps, university career</p>
                  <p className="figma-174">{`centers, & coaching teams.`}</p>
                </div>
              </div>
              <div className="figma-493" data-node-id="173:3205" data-name="List">
                <div className="figma-211" data-node-id="173:3206" data-name="Item">
                  <div className="figma-494" data-node-id="173:3207" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer2} />
                  </div>
                  <div className="figma-19" data-node-id="173:3209" data-name="Container">
                    <div className="figma-36" data-node-id="173:3210">
                      <p className="figma-30">Bulk Student Licenses</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3211" data-name="Item">
                  <div className="figma-494" data-node-id="173:3212" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer2} />
                  </div>
                  <div className="figma-19" data-node-id="173:3214" data-name="Container">
                    <div className="figma-36" data-node-id="173:3215">
                      <p className="figma-30">Coach Analytics Dashboard</p>
                    </div>
                  </div>
                </div>
                <div className="figma-211" data-node-id="173:3216" data-name="Item">
                  <div className="figma-494" data-node-id="173:3217" data-name="Container">
                    <img alt="" className="figma-23" src={pricingImgContainer2} />
                  </div>
                  <div className="figma-19" data-node-id="173:3219" data-name="Container">
                    <div className="figma-36" data-node-id="173:3220">
                      <p className="figma-30">Dedicated Account Lead</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="figma-99" data-node-id="173:3221" data-name="Link:margin">
            <div className="figma-495">
              <div className="figma-496" data-node-id="173:3222" data-name="Link">
                <div className="figma-497" data-node-id="173:3223">
                  <p className="figma-341">Contact Sales</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FAQ() {
  return (
    <div className="figma-510" data-node-id="173:3260" data-name="Section - 10. FAQ ACCORDION">
      <div className="figma-511" data-node-id="173:3261" data-name="Container">
        <div className="figma-75" data-node-id="173:3262" data-name="Margin">
          <div className="figma-76" data-node-id="173:3263" data-name="Container">
            <div className="figma-77" data-node-id="173:3264">
              <p className="figma-78">CLEAR CLARITY</p>
            </div>
          </div>
        </div>
        <div className="figma-79" data-node-id="173:3265">
          <p className="figma-80">Questions, answered.</p>
        </div>
        <div className="figma-81" data-node-id="173:3266" data-name="Margin">
          <div className="figma-76" data-node-id="173:3267" data-name="Container">
            <div className="figma-83" data-node-id="173:3268">
              <p className="figma-85">Everything you need to know about how Intervucopilot operates during your job search.</p>
            </div>
          </div>
        </div>
      </div>
      <div className="figma-512" data-node-id="173:3269" data-name="Container">
        <div className="figma-513" data-node-id="173:3270" data-name="Details - FAQ 1">
          <div className="figma-99" data-node-id="173:3271" data-name="Slot → Summary">
            <div className="figma-131">
              <div className="figma-19" data-node-id="173:3272" data-name="Container">
                <div className="figma-370" data-node-id="173:3273">
                  <p className="figma-514">Will my interviewer know I am using the Desktop HUD?</p>
                </div>
              </div>
              <div className="figma-515" data-node-id="173:3274" data-name="Container">
                <img alt="" className="figma-23" src={faqImgContainer} />
              </div>
            </div>
          </div>
        </div>
        <div className="figma-513" data-node-id="173:3276" data-name="Details - FAQ 2">
          <div className="figma-99" data-node-id="173:3277" data-name="Slot → Summary">
            <div className="figma-131">
              <div className="figma-19" data-node-id="173:3278" data-name="Container">
                <div className="figma-370" data-node-id="173:3279">
                  <p className="figma-514">How does Intervucopilot ground answers in my real work?</p>
                </div>
              </div>
              <div className="figma-515" data-node-id="173:3280" data-name="Container">
                <img alt="" className="figma-23" src={faqImgContainer} />
              </div>
            </div>
          </div>
        </div>
        <div className="figma-513" data-node-id="173:3282" data-name="Details - FAQ 3">
          <div className="figma-99" data-node-id="173:3283" data-name="Slot → Summary">
            <div className="figma-131">
              <div className="figma-19" data-node-id="173:3284" data-name="Container">
                <div className="figma-370" data-node-id="173:3285">
                  <p className="figma-514">Can I delete my transcripts and session logs?</p>
                </div>
              </div>
              <div className="figma-515" data-node-id="173:3286" data-name="Container">
                <img alt="" className="figma-23" src={faqImgContainer} />
              </div>
            </div>
          </div>
        </div>
        <div className="figma-513" data-node-id="173:3288" data-name="Details - FAQ 4">
          <div className="figma-99" data-node-id="173:3289" data-name="Slot → Summary">
            <div className="figma-131">
              <div className="figma-19" data-node-id="173:3290" data-name="Container">
                <div className="figma-370" data-node-id="173:3291">
                  <p className="figma-514">Can I use Intervucopilot for mock practice before real rounds?</p>
                </div>
              </div>
              <div className="figma-515" data-node-id="173:3292" data-name="Container">
                <img alt="" className="figma-23" src={faqImgContainer} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FinalCTA() {
  return (
    <div className="figma-516" data-node-id="173:3295" data-name="Section - 11. FINAL MEMORABLE CTA (Clean Light Theme with Blue Radiance)">
      <div className="figma-88" data-node-id="173:3296" data-name="Background+Border+Shadow">
        <div className="figma-89" data-node-id="173:3297" data-name="Soft ambient glow" />
        <div className="figma-517" data-node-id="173:3298" data-name="Mascot Micro Accent:margin">
          <div className="figma-518" data-node-id="173:3299" data-name="Mascot Micro Accent">
            <div className="figma-519" data-node-id="173:3300" data-name="Intervucopilot Intelligent Mascot">
              <img alt="" className="figma-520" src={finalctaImgSaiiaIntelligentMascot} />
            </div>
          </div>
        </div>
        <div className="figma-90" data-node-id="173:3301" data-name="Heading 2">
          <div className="figma-265" data-node-id="173:3302">
            <p className="figma-92">Your next interview starts</p>
            <p className="figma-93">before you enter the room.</p>
          </div>
        </div>
        <div className="figma-521" data-node-id="173:3303" data-name="Margin">
          <div className="figma-522" data-node-id="173:3304" data-name="Container">
            <div className="figma-83" data-node-id="173:3305">
              <p className="figma-84">Join ambitious engineers and professionals turning interview anxiety</p>
              <p className="figma-85">into structured, context-rich confidence.</p>
            </div>
          </div>
        </div>
        <div className="figma-523" data-node-id="173:3306" data-name="Container">
          <a href="/auth/signup" className="figma-435" data-node-id="173:3307" data-name="Link">
            <div className="figma-76" data-node-id="173:3308" data-name="Container">
              <div className="figma-524" data-node-id="173:3309">
                <p className="figma-21">Create Free Account</p>
              </div>
            </div>
            <div className="figma-22" data-node-id="173:3310" data-name="Container">
              <img alt="" className="figma-23" src={finalctaImgContainer} />
            </div>
          </a>
          <div className="figma-525" data-node-id="173:3312" data-name="Button">
            <div className="figma-22" data-node-id="173:3313" data-name="Container">
              <img alt="" className="figma-23" src={finalctaImgContainer1} />
            </div>
            <div className="figma-5" data-node-id="173:3315" data-name="Container">
              <div className="figma-64">
                <div className="figma-526" data-node-id="173:3316">
                  <p className="figma-21">Download Desktop App</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-527" data-node-id="173:3317" data-name="Margin">
          <div className="figma-76" data-node-id="173:3318" data-name="Container">
            <div className="figma-528" data-node-id="173:3319">
              <p className="figma-78">No credit card required • macOS and Windows compatible • Ready in 2 minutes</p>
            </div>
          </div>
        </div>
        <div className="figma-529" data-node-id="188:567">
          <div className="figma-530">
            <div className="figma-531">
              <div className="figma-532">
                <img alt="" className="figma-287" src={finalctaImgEllipse3} />
              </div>
            </div>
          </div>
        </div>
        <div className="figma-533" data-node-id="188:505">
          <div className="figma-534" data-node-id="188:506">
            <div className="figma-535">
              <div className="figma-536">
                <div className="figma-537">
                  <img alt="" className="figma-287" src={finalctaImgLine9} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-538" data-node-id="188:507">
            <div className="figma-539">
              <div className="figma-540">
                <div className="figma-537">
                  <img alt="" className="figma-287" src={finalctaImgLine10} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-541" data-node-id="188:508">
            <div className="figma-542">
              <div className="figma-543">
                <div className="figma-544">
                  <img alt="" className="figma-287" src={finalctaImgLine11} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-545" data-node-id="188:509">
            <div className="figma-546">
              <div className="figma-547">
                <div className="figma-544">
                  <img alt="" className="figma-287" src={finalctaImgLine12} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-548" data-node-id="188:510">
            <div className="figma-549">
              <div className="figma-550">
                <div className="figma-544">
                  <img alt="" className="figma-287" src={finalctaImgLine13} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-551" data-node-id="188:511">
            <div className="figma-552">
              <div className="figma-553">
                <div className="figma-544">
                  <img alt="" className="figma-287" src={finalctaImgLine14} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-554" data-node-id="188:512">
            <div className="figma-555">
              <div className="figma-556">
                <div className="figma-557">
                  <img alt="" className="figma-287" src={finalctaImgLine15} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-558" data-node-id="188:513">
            <div className="figma-559">
              <div className="figma-560">
                <div className="figma-557">
                  <img alt="" className="figma-287" src={finalctaImgLine16} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-561" data-node-id="188:514">
            <div className="figma-562">
              <div className="figma-563">
                <div className="figma-557">
                  <img alt="" className="figma-287" src={finalctaImgLine17} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-564" data-node-id="188:515">
            <div className="figma-565">
              <div className="figma-566">
                <div className="figma-567">
                  <img alt="" className="figma-287" src={finalctaImgLine18} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-568" data-node-id="188:516">
            <div className="figma-569">
              <div className="figma-570">
                <div className="figma-567">
                  <img alt="" className="figma-287" src={finalctaImgLine19} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-571" data-node-id="188:517">
            <div className="figma-572">
              <div className="figma-573">
                <div className="figma-567">
                  <img alt="" className="figma-287" src={finalctaImgLine20} />
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-574" data-node-id="188:504">
          <div className="figma-575">
            <div className="figma-531">
              <div className="figma-532">
                <img alt="" className="figma-287" src={finalctaImgEllipse2} />
              </div>
            </div>
          </div>
        </div>
        <div className="figma-576" data-node-id="188:518">
          <div className="figma-577" data-node-id="188:519">
            <div className="figma-578">
              <div className="figma-579">
                <div className="figma-580">
                  <img alt="" className="figma-287" src={finalctaImgLine38} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-581" data-node-id="188:520">
            <div className="figma-582">
              <div className="figma-583">
                <div className="figma-580">
                  <img alt="" className="figma-287" src={finalctaImgLine39} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-584" data-node-id="188:521">
            <div className="figma-585">
              <div className="figma-586">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine40} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-588" data-node-id="188:522">
            <div className="figma-589">
              <div className="figma-590">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine41} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-591" data-node-id="188:523">
            <div className="figma-592">
              <div className="figma-593">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine42} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-594" data-node-id="188:524">
            <div className="figma-595">
              <div className="figma-596">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine43} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-597" data-node-id="188:525">
            <div className="figma-598">
              <div className="figma-599">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine44} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-600" data-node-id="188:526">
            <div className="figma-601">
              <div className="figma-602">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine45} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-603" data-node-id="188:527">
            <div className="figma-604">
              <div className="figma-605">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine46} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-606" data-node-id="188:528">
            <div className="figma-607">
              <div className="figma-608">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine47} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-609" data-node-id="188:529">
            <div className="figma-610">
              <div className="figma-611">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine48} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-612" data-node-id="188:530">
            <div className="figma-613">
              <div className="figma-614">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine49} />
                </div>
              </div>
            </div>
          </div>
          <div className="figma-615" data-node-id="188:531">
            <div className="figma-616">
              <div className="figma-617">
                <div className="figma-587">
                  <img alt="" className="figma-287" src={finalctaImgLine50} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef(null);
  return (
    <div className={`figma-618${menuOpen ? ' landing-menu-open' : ''}`} data-node-id="173:3376" data-name="Header"
      onKeyDown={event => {
        if (event.key === 'Escape' && menuOpen) {
          setMenuOpen(false);
          menuButtonRef.current.focus();
        }
      }}>
      <div className="figma-619" data-node-id="173:3377" data-name="Container">
        <div className="figma-620">
          <div className="figma-621" data-node-id="187:465" data-name="Container">
            <div className="figma-622" data-node-id="187:466" data-name="Background">
              <div className="figma-623" data-node-id="187:467" data-name="Container">
                <img alt="" className="figma-23" src={headerImgContainer} />
              </div>
            </div>
            <div className="figma-19" data-node-id="187:469" data-name="Container">
              <div className="figma-624" data-node-id="187:470">
                <p className="figma-514">Intervucopilot</p>
              </div>
            </div>
          </div>
          <button ref={menuButtonRef} type="button" className="landing-menu-toggle"
            aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={menuOpen} aria-controls="landing-navigation landing-account-links"
            onClick={() => setMenuOpen(open => !open)}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              {menuOpen ? <path d="M6 6l12 12M6 18L18 6" /> : <path d="M4 6h16M4 12h16M4 18h16" />}
            </svg>
          </button>
          <div className="figma-625" id="landing-navigation" role="navigation" aria-label="Main navigation" data-node-id="173:3385" data-name="Nav"
            onClick={event => { if (event.target.closest('a')) setMenuOpen(false); }}>
            <a href="#features" className="figma-19" data-node-id="173:3386" data-name="Link">
              <div className="figma-626" data-node-id="173:3387">
                <p className="figma-21">Features</p>
              </div>
            </a>
            <a href="#how-it-works" className="figma-19" data-node-id="173:3388" data-name="Link">
              <div className="figma-627" data-node-id="173:3389">
                <p className="figma-21">How It Works</p>
              </div>
            </a>
            <a href="#product" className="figma-19" data-node-id="173:3390" data-name="Link">
              <div className="figma-627" data-node-id="173:3391">
                <p className="figma-21">Product</p>
              </div>
            </a>
            <a href="#pricing" className="figma-19" data-node-id="173:3392" data-name="Link">
              <div className="figma-627" data-node-id="173:3393">
                <p className="figma-21">Pricing</p>
              </div>
            </a>
            <a href="#faq" className="figma-19" data-node-id="173:3394" data-name="Link">
              <div className="figma-627" data-node-id="173:3395">
                <p className="figma-21">FAQ</p>
              </div>
            </a>
          </div>
          <div className="figma-628" id="landing-account-links" data-node-id="173:3396" data-name="Container">
            <a href="/auth/login" className="figma-629" data-node-id="173:3397" data-name="Link">
              <div className="figma-630" data-node-id="173:3398">
                <p className="figma-21">Log in</p>
              </div>
            </a>
            <a href="/auth/signup" className="figma-631" data-node-id="173:3399" data-name="Link">
              <div className="figma-19" data-node-id="173:3400" data-name="Container">
                <div className="figma-632" data-node-id="173:3401">
                  <p className="figma-341">Get Started</p>
                </div>
              </div>
              <div className="figma-633" data-node-id="173:3402" data-name="Container">
                <img alt="" className="figma-23" src={headerImgContainer1} />
              </div>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

function Footer() {
  return (
    <div className="figma-634" data-node-id="173:3320" data-name="Footer">
      <div className="figma-99" data-node-id="173:3321" data-name="Container">
        <div className="figma-635">
          <div className="figma-636" data-node-id="173:3322" data-name="Container">
            <div className="figma-637" data-node-id="173:3323" data-name="Container">
              <div className="figma-211" data-node-id="173:3324" data-name="Container">
                <div className="figma-638" data-node-id="173:3325" data-name="Intervucopilot AI Logo">
                  <div className="figma-58">
                    <img alt="" className="figma-639" src={footerImgSaiiaAiLogo} />
                  </div>
                </div>
                <div className="figma-19" data-node-id="173:3326" data-name="Container">
                  <div className="figma-43" data-node-id="173:3327" data-name="Container">
                    <div className="figma-640" data-node-id="173:3328">
                      <p className="figma-105">Intervucopilot</p>
                    </div>
                  </div>
                  <div className="figma-43" data-node-id="173:3329" data-name="Container">
                    <div className="figma-641" data-node-id="173:3330">
                      <p className="figma-45">SMART AI INTERVIEW ASSISTANT</p>
                    </div>
                  </div>
                </div>
              </div>
              <div className="figma-642" data-node-id="173:3331" data-name="Container">
                <div className="figma-643" data-node-id="173:3332">
                  <p className="figma-107">Empowering modern talent teams with tactical AI telemetry, candidate sentiment intelligence, and real-time structured interview scoring.</p>
                </div>
              </div>
            </div>
            <div className="figma-644" data-node-id="173:3333" data-name="Container">
              <div className="figma-43" data-node-id="173:3334" data-name="Container">
                <div className="figma-645" data-node-id="173:3335">
                  <p className="figma-8">PRODUCT</p>
                </div>
              </div>
              <a href="#features" className="figma-43" data-node-id="173:3336" data-name="Link">
                <div className="figma-646" data-node-id="173:3337">
                  <p className="figma-341">Features</p>
                </div>
              </a>
              <a href="#how-it-works" className="figma-43" data-node-id="173:3338" data-name="Link">
                <div className="figma-646" data-node-id="173:3339">
                  <p className="figma-341">Workflow Engine</p>
                </div>
              </a>
              <a href="#product" className="figma-43" data-node-id="173:3340" data-name="Link">
                <div className="figma-646" data-node-id="173:3341">
                  <p className="figma-341">Telemetry Cockpit</p>
                </div>
              </a>
              <a href="#pricing" className="figma-43" data-node-id="173:3342" data-name="Link">
                <div className="figma-646" data-node-id="173:3343">
                  <p className="figma-341">Pricing Tiers</p>
                </div>
              </a>
            </div>
            <div className="figma-647" data-node-id="173:3344" data-name="Container">
              <div className="figma-43" data-node-id="173:3345" data-name="Container">
                <div className="figma-645" data-node-id="173:3346">
                  <p className="figma-8">RESOURCES</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:3347" data-name="Link">
                <div className="figma-646" data-node-id="173:3348">
                  <p className="figma-341">Documentation</p>
                </div>
              </div>
              <a href="#faq" className="figma-43" data-node-id="173:3349" data-name="Link">
                <div className="figma-646" data-node-id="173:3350">
                  <p className="figma-341">FAQ</p>
                </div>
              </a>
              <div className="figma-43" data-node-id="173:3351" data-name="Link">
                <div className="figma-646" data-node-id="173:3352">
                  <p className="figma-341">{`Security & Compliance`}</p>
                </div>
              </div>
              <div className="figma-43" data-node-id="173:3353" data-name="Link">
                <div className="figma-646" data-node-id="173:3354">
                  <p className="figma-341">API References</p>
                </div>
              </div>
            </div>
            <div className="figma-648" data-node-id="173:3355" data-name="Container">
              <div className="figma-43" data-node-id="173:3356" data-name="Container">
                <div className="figma-645" data-node-id="173:3357">
                  <p className="figma-8">{`ACCOUNT & LEGAL`}</p>
                </div>
              </div>
              <a href="/auth/login" className="figma-43" data-node-id="173:3358" data-name="Link">
                <div className="figma-646" data-node-id="173:3359">
                  <p className="figma-341">Log in</p>
                </div>
              </a>
              <a href="/auth/signup" className="figma-43" data-node-id="173:3360" data-name="Link">
                <div className="figma-646" data-node-id="173:3361">
                  <p className="figma-341">Create Account</p>
                </div>
              </a>
              <a href="#privacy" className="figma-43" data-node-id="173:3362" data-name="Link">
                <div className="figma-646" data-node-id="173:3363">
                  <p className="figma-341">Privacy Policy</p>
                </div>
              </a>
              <a href="#privacy" className="figma-43" data-node-id="173:3364" data-name="Link">
                <div className="figma-646" data-node-id="173:3365">
                  <p className="figma-341">Terms of Service</p>
                </div>
              </a>
            </div>
          </div>
          <div className="figma-649" data-node-id="173:3366" data-name="HorizontalBorder">
            <div className="figma-5" data-node-id="173:3367" data-name="Container">
              <div className="figma-6">
                <div className="figma-29" data-node-id="173:3368">
                  <p className="figma-30">© 2025 Intervucopilot AI Systems Inc. All rights reserved.</p>
                </div>
              </div>
            </div>
            <div className="figma-5" data-node-id="173:3369" data-name="Container">
              <div className="figma-650">
                <a href="#privacy" className="figma-19" data-node-id="173:3370" data-name="Link">
                  <div className="figma-651" data-node-id="173:3371">
                    <p className="figma-30">Privacy</p>
                  </div>
                </a>
                <a href="#privacy" className="figma-19" data-node-id="173:3372" data-name="Link">
                  <div className="figma-651" data-node-id="173:3373">
                    <p className="figma-30">Terms</p>
                  </div>
                </a>
                <div className="figma-19" data-node-id="173:3374" data-name="Link">
                  <div className="figma-651" data-node-id="173:3375">
                    <p className="figma-30">Security</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
export default function LandingPage() {
  return (
    <div className="landing-page">
      <header className="landing-header"><Header /></header>
      <main className="landing-main">
        <section id="hero" aria-label="Interview preparation" className="landing-hero-band">
          <div className="landing-section landing-hero"><Hero /></div>
        </section>
        <section id="problem" aria-label="The preparation gap" className="landing-section landing-problem"><Problem /></section>
        <section id="how-it-works" aria-label="Workflow" className="landing-section landing-workflow"><Workflow /></section>
        <section id="features" aria-label="Features" className="landing-section landing-features"><Features /></section>
        <section id="platforms" aria-label="Platforms" className="landing-section landing-platforms"><Platforms /></section>
        <section id="trusted" aria-label="Trusted by candidates" className="landing-section landing-trusted"><Trusted /></section>
        <section id="product" aria-label="Product showcase" className="landing-section landing-product"><Product /></section>
        <section id="preparation" aria-label="Preparation workflow" className="landing-section landing-preparation"><Preparation /></section>
        <section id="desktop" aria-label="Desktop app" className="landing-section landing-desktop"><Desktop /></section>
        <section id="privacy" aria-label="Privacy and control" className="landing-section landing-privacy"><Privacy /></section>
        <section id="pricing" aria-label="Pricing" className="landing-section landing-pricing"><Pricing /></section>
        <section id="faq" aria-label="Frequently asked questions" className="landing-section landing-faq"><FAQ /></section>
        <section id="get-started" aria-label="Get started" className="landing-section landing-cta"><FinalCTA /></section>
      </main>
      <footer className="landing-footer"><Footer /></footer>
    </div>
  )
}
