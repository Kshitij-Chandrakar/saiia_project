import { createMessage, MESSAGE_TYPES } from '../core/messages.js'

const statusNode = document.querySelector('#status')
document.querySelector('#refresh').addEventListener('click', refresh)
refresh()

async function refresh() {
  const response = await chrome.runtime.sendMessage(createMessage(MESSAGE_TYPES.getStatus))
  statusNode.textContent = JSON.stringify(response?.status || response?.error || {}, null, 2)
}
