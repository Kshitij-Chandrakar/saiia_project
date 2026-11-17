import React, {useState} from 'react'
import {createRoot} from 'react-dom/client'
import MainAnswerDisplay from '../../src/components/MainAnswerDisplay.jsx'
import DesktopAnswerHistory from '../../src/components/DesktopAnswerHistory.jsx'
import OverlayWindow from '../../src/components/OverlayWindow.jsx'
import '../../src/styles/glass.css'
const canonical='**Purpose**\n\nSystem design describes components and their relationships.\n\n1. Establish requirements.\n2. Compare tradeoffs.\n\n```python\ndef identity(value):\n    return value\n```'
const api={answerDiagram:async action=>({ok:true,data:action==='history'?{items:[{id:'synthetic-saved',question_text:'Explain system design.',answer_text:canonical}]}:{eligible:false}}),onAnswerDiagramInvalidated:()=>()=>{}}
export default function Fixture(){
 const [state,setState]=useState({text:'',streaming:true})
 window.setPresentation=value=>setState(value)
 window.finishPresentation=()=>setState({text:canonical,streaming:false})
 return <><section id="main"><MainAnswerDisplay answer={state.text}/></section>
 <section id="overlay"><OverlayWindow overlayState={{visible:true,answer:state.text,provider:'synthetic',answerDisplayMode:'answer',answerRevealActive:state.streaming,answerFullAvailable:Boolean(state.text)}}/></section>
 <section id="history"><DesktopAnswerHistory sessionId="synthetic-session" api={api}/></section></>
}
createRoot(document.getElementById('root')).render(<Fixture/>)
