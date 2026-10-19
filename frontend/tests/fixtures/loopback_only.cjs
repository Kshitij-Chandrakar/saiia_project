// Test-process-only guard, also inherited by Node subprocesses via NODE_OPTIONS.
const net = require('node:net')
const dns = require('node:dns')
function allowed(host) {
  if (host == null || ['localhost', '127.0.0.1', '::1', '[::1]'].includes(host)) return
  throw Error('External network forbidden in isolated tests')
}
const connect = net.Socket.prototype.connect
net.Socket.prototype.connect = function (...args) {
  const options = Array.isArray(args[0]) ? args[0][0] : args[0]
  // String-only addresses are local pipe paths; TCP uses a port or options.
  allowed(typeof options === 'object' ? options.host : typeof options === 'number' && typeof args[1] === 'string' ? args[1] : undefined)
  return connect.apply(this, args)
}
const lookup = dns.lookup
dns.lookup = function (host, ...args) { allowed(host); return lookup.call(this, host, ...args) }
