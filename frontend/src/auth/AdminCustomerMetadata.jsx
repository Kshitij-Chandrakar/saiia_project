import AdminHelp from './AdminHelp';

// Definitions follow the fixed administration_read/customer_metadata projections.
const metadataFields = {
  user_id: ['Account ID', 'A unique reference used to identify this account.'],
  email: ['Email', 'The email address currently recorded for this account.'],
  registered_at: ['Registered', 'When the sign-in account was created.', 'date'],
  email_verified: ['Email verified', 'Whether the sign-in service records this email address as confirmed.'],
  auth_provider_labels: ['Sign-in methods', 'Sign-in providers linked to this account; a listed provider does not guarantee that sign-in will succeed.', 'providers'],
  account_access_state: ['Account restriction status', 'Whether staff, deletion or restore safeguards currently restrict this account; plan allowances and expiry are checked separately.', 'status'],
  staff_restriction_state: ['Staff restriction', 'Whether an administrator has blocked the customer\'s product access.', 'staff_status'],
  deletion_restricted: ['Accepted deletion request', 'Whether this account has an accepted customer deletion request; this does not mean cleanup is complete.'],
  last_product_activity_at: ['Last recorded activity', 'The latest successful session creation or finalized product-use record since tracking began, not the last login or online presence.', 'date'],
  activity_coverage: ['Activity coverage', 'Which successful product actions are tracked; older activity may be unavailable.', 'status'],
  plan_code: ['Plan code', 'The plan identifier in the account\'s current plan assignment; it does not alone establish paid access.'],
  subscription_state: ['Plan assignment status', 'Whether the assigned plan is active and within its validity dates; billing and account restrictions are separate.', 'status'],
  data_as_of: ['Data as of', 'When the account metadata query started; separately retrieved sections can have slightly different retrieval times.', 'date'],
  resume_count: ['Resumes', 'The number of saved resume records not marked deleted; private resume content is not shown.'],
  active_resume_count: ['Active resumes', 'The number of nondeleted resumes selected as active.'],
  resume_processing_state: ['Resume processing', 'Counts of nondeleted resumes at each processing stage.', 'processing'],
  session_count: ['Sessions', 'The number of saved interview sessions, including sessions that have ended.'],
  last_session_started_at: ['Latest session start', 'The most recent recorded session start time, if available.', 'date'],
  last_session_ended_at: ['Latest session end', 'The most recent recorded end time among saved sessions, if available.', 'date'],
  job_context_count: ['Saved job details', 'The number of saved job-context records; their private content is not shown.'],
  status_coverage: ['Resource coverage', 'These counts describe currently stored records, not a complete lifetime history.', 'status'],
  marketing_opt_in: ['Marketing opt-in', 'Whether the customer agreed to promotional emails; unsubscribe, suppression and delivery checks still apply.'],
  marketing_preference_updated_at: ['Marketing preference updated', 'The later of the recorded promotional-email opt-in and opt-out times.', 'date'],
  terms_version: ['Terms version', 'The recorded agreement version, shown only when terms acceptance is recorded.'],
  privacy_version: ['Privacy policy version', 'The recorded agreement version, shown only when privacy-policy acceptance is recorded.'],
  consent_accepted_at: ['Latest policy acceptance', 'The later of the recorded terms and privacy-policy acceptance times.', 'date'],
  paid_status: ['Payment operation status', 'The checkout operation\'s recorded stage; only a confirmed result establishes its verified outcome.', 'status'],
  renewal_state: ['Provider subscription status', 'The last recorded payment-provider subscription status; missing information does not establish cancellation.', 'status'],
  cancellation_state: ['Cancellation status', 'Whether the recorded provider outcome confirms renewal has ended; a request alone is not confirmation.', 'status'],
  command_state: ['Cancellation request status', 'Progress of this cancellation command, separate from product access and provider-confirmed cancellation.', 'status'],
  kind: ['Cleanup scope', 'The scope of the existing customer-authorized cleanup task.', 'status'],
  state: ['Cleanup task status', 'The task\'s current progress; verified primary cleanup does not mean all billing, retention or external obligations are finished.', 'status'],
  revision: ['Task revision', 'A version number used to prevent retrying an outdated task state.'],
  attempts: ['Attempts', 'The number of attempts recorded for this cleanup task, not a count of successful deletions.'],
};

const statuses = {
  restricted: 'Restricted', unrestricted: 'No listed account restriction', active: 'Active', expired_or_inactive: 'Expired or inactive',
  successful_commits_since_instrumentation: 'Session starts and finalized product-use records since tracking began', not_instrumented: 'Activity tracking unavailable', current_controlled_rows: 'Currently stored records only',
  uploaded: 'Uploaded', extracting: 'Reading resume', needs_review: 'Review needed', indexing: 'Preparing resume search', ready: 'Ready', failed: 'Failed', timeout: 'Timed out', cancelled: 'Cancelled', deleted: 'Deleted',
  prepared: 'Prepared', creating: 'Creating checkout', uncertain: 'Outcome uncertain', pending: 'Pending', confirmed: 'Confirmed', expired: 'Expired',
  authenticated: 'Payment authorization recorded', halted: 'On hold', completed: 'Completed', created: 'Created', paused: 'Paused', resumed: 'Resumed',
  unknown: 'Outcome unknown', none: 'No cancellation request recorded', requested: 'Requested', running: 'Running', blocked: 'Blocked', succeeded: 'Succeeded',
  primary_verified: 'Primary content cleanup verified', account: 'Whole-account personal content', session: 'One session', history: 'All session history',
};
const providers = { email: 'Email', google: 'Google', github: 'GitHub', apple: 'Apple', azure: 'Microsoft', phone: 'Phone' };
function Unknown({ value }) { return <><span>Unknown value</span><details className="ac-technical"><summary>Technical value</summary><code>{String(value)}</code></details></>; }
export function MetadataValue({ value, type }) {
  if (value === null || value === undefined) return 'Unavailable';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (type === 'date') {
    const date = new Date(value);
    if (typeof value !== 'string' || !Number.isFinite(date.getTime())) return <Unknown value={value} />;
    return <><time dateTime={value}>{new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(date)} UTC</time><details className="ac-technical"><summary>Exact timestamp</summary><code>{value}</code></details></>;
  }
  if (type === 'status') return statuses[value] || <Unknown value={value} />;
  if (type === 'staff_status') return ({ restricted: 'Staff-restricted', unrestricted: 'Not staff-restricted' })[value] || <Unknown value={value} />;
  if (type === 'providers') return Array.isArray(value) ? value.length ? value.map(provider => providers[provider] || `Unrecognized provider (${provider})`).join(', ') : 'No linked providers recorded' : <Unknown value={value} />;
  if (type === 'processing') return typeof value === 'object' && !Array.isArray(value) ? Object.keys(value).length ? <ul className="ac-processing-counts">{Object.entries(value).map(([state, count]) => <li key={state}><MetadataValue value={state} type="status" />: <MetadataValue value={count} /></li>)}</ul> : 'No nondeleted resume stages recorded' : <Unknown value={value} />;
  return String(value);
}
function Fields({ data, fields }) {
  return <dl>{fields.map(field => {
    const [label, help, type] = metadataFields[field] || ['Unrecognized field', 'This field is not yet described. Treat its meaning as unknown.'];
    return <div key={field}><dt><span>{label}</span><AdminHelp label={label}>{help}</AdminHelp></dt><dd><MetadataValue value={data[field]} type={type} />{!metadataFields[field] && <details className="ac-technical"><summary>Technical field</summary><code>{field}</code></details>}</dd></div>;
  })}</dl>;
}
function Heading({ title, help, level = 3 }) { const Tag = `h${level}`; return <Tag className="ac-metadata-heading" aria-label={title}>{title}<AdminHelp label={title}>{help}</AdminHelp></Tag>; }
function Action({ label, help, onClick }) { return <span className="ac-metadata-action"><button onClick={onClick}>{label}</button><AdminHelp label={label}>{help}</AdminHelp></span>; }

export default function AdminCustomerMetadata({ detail, role, onRestrict, onRestore, onCancelRenewal, onRetry, lastCommand, onRefreshCancellation }) {
  return <section className="ac-customer-metadata" aria-label="Selected customer metadata">
    <Heading level={2} title="Account metadata" help="Basic account details, linked sign-in providers and recorded access restrictions. Private customer content is not shown." />
    <Fields data={detail} fields={['user_id','email','registered_at','email_verified','auth_provider_labels','account_access_state','staff_restriction_state','deletion_restricted','last_product_activity_at','activity_coverage','plan_code','subscription_state','data_as_of']} />
    {detail.resources && <section aria-label="Resource metadata"><Heading title="Resource summary" help="Counts and processing stages of saved resumes, sessions and job details. Private content is not shown." /><Fields data={detail.resources} fields={Object.keys(detail.resources)} /></section>}
    {detail.consent && <section aria-label="Consent metadata"><Heading title="Consent and preferences" help="Recorded policy agreements and preferences for promotional emails." /><Fields data={detail.consent} fields={Object.keys(detail.consent)} /></section>}
    <div className="ac-metadata-actions"><Action label="Restrict product access" help="Blocks product use without cancelling billing or deleting account data." onClick={onRestrict} />{role === 'super_admin' && <Action label="Restore staff-restricted access" help="Removes only the staff restriction. Deletion restrictions, plan limits and expiry still apply." onClick={onRestore} />}</div>
    {detail.subscription && <section aria-label="Subscription support"><Heading title="Subscription status" help="Recorded checkout and provider renewal status. These facts are separate from the customer's product access." />{detail.subscription.operations.map(operation => <div key={operation.subscription_id}><Fields data={operation} fields={['paid_status','renewal_state','cancellation_state']} /><Action label="Request renewal cancellation" help="Requests an end to future renewals. Provider confirmation is required; existing paid access remains until expiry unless separately restricted." onClick={() => onCancelRenewal(operation)} /></div>)}{detail.subscription.operations.length === 0 && <p>No subscription operations recorded.</p>}
      {lastCommand && <div role="status"><Fields data={{ command_state: lastCommand.state }} fields={['command_state']} /><Action label="Refresh cancellation status" help="Checks this cancellation request's recorded outcome; refreshing does not send a new cancellation request." onClick={onRefreshCancellation} /></div>}
    </section>}
    {detail.privacy && <section aria-label="Existing privacy cleanup tasks"><Heading title="User-authorized privacy requests" help="Cleanup tasks for requests already authorized by the customer. Staff cannot initiate deletion, enlarge its scope or mark uncertain work complete." /><p>Restriction, primary cleanup and retained obligations are separate. Staff cannot start deletion or mark uncertain work complete.</p>{detail.privacy.tasks?.map(task => <div key={task.task_id}><Fields data={task} fields={['kind','state','revision','attempts']} />{task.retry_available && <Action label="Review eligible cleanup retry" help="Reviews another attempt at this existing authorized task. Eligibility, holds and the original scope are still enforced." onClick={() => onRetry(task)} />}</div>)}</section>}
  </section>;
}
