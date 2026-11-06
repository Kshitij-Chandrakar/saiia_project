import React,{useState} from 'react'
import {createRoot} from 'react-dom/client'
import DiagramSection from '../../src/components/DiagramSection.jsx'
import MainAnswerDisplay from '../../src/components/MainAnswerDisplay.jsx'
import DesktopAnswerHistory from '../../src/components/DesktopAnswerHistory.jsx'
const api={answerDiagram:(...args)=>window.diagramRequest(...args),onAnswerDiagramInvalidated:callback=>{window.invalidateDiagram=callback;return()=>{window.invalidateDiagram=null}}}
export default function Fixture(){
 const [source,setSource]=useState({session_id:'30000000-0000-4000-8000-000000000001',request_id:'first',canonical_question:'Design a queue',canonical_answer:'API sends tasks to Queue.'})
 window.changeDiagramSource=next=>setSource({...next,canonical_question:'Design a queue',canonical_answer:'API sends tasks to Queue.'})
 return <main style={{padding:16,boxSizing:'border-box',width:'100%'}}>
 <p id="canonical-answer">API sends tasks to Queue.</p>
 {new URLSearchParams(location.search).has('history')?<DesktopAnswerHistory sessionId={source.session_id} api={api}/>:<MainAnswerDisplay answer="API sends tasks to Queue." source={source} api={api}/>}
 </main>
}
createRoot(document.getElementById('root')).render(<Fixture/> )
