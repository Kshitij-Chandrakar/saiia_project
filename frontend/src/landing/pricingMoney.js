export function money(price) {
  const amount = BigInt(price.amount_minor), factor = 10n ** BigInt(price.exponent);
  const whole = (amount / factor).toLocaleString('en-IN');
  const fraction = (amount % factor).toString().padStart(Number(price.exponent), '0');
  return `${price.currency === 'INR' ? '\u20b9' : price.currency + ' '}${whole}${amount % factor ? '.' + fraction : ''}`;
}
export function annualComparison(month, year) {
  if (!month || !year || month.currency !== year.currency || month.exponent !== year.exponent) return null;
  const full = BigInt(month.amount_minor) * 12n, total = BigInt(year.amount_minor);
  return {full: money({...month,amount_minor:String(full)}),saving:full > total ? String((full-total)*100n/full) : '0',equivalent:money({...year,amount_minor:String((total+6n)/12n)})};
}
