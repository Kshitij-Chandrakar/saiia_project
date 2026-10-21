import React from 'react'
import DiagramSection from './DiagramSection.jsx'
import AnswerText from './AnswerText.jsx'

// Main window only. The overlay keeps its existing AnswerPanel.
export default function MainAnswerDisplay({ answer, source, api }) {
  return <div className="glass-card">
    <p className="section-title">Displayed answer</p>
    <div className="answer-preview"><AnswerText text={answer || 'The active overlay answer will appear here once SAIIA completes a request.'} /></div>
    {source && <DiagramSection source={source} api={api} />}
  </div>
}
