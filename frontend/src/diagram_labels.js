export function lines(text, width = 22) {
  return String(text).match(new RegExp(`.{1,${width}}(?:\\s|$)|.{1,${width}}`, 'gu'))?.map(line => line.trim()) || ['']
}
