import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ShieldCheck, LayoutDashboard, Plus, BookOpen, ArrowUpRight, ArrowRight, Camera, Check, CheckCircle2, Clock3, Download, FileText, RefreshCw, UploadCloud, X, AlertTriangle, Radio, Car, ChevronRight, Mail, Network } from 'lucide-react';
import AgentGraph from './AgentGraph';
import { API, getClaim, getDemos, mask, money, redact, request, safeLink, title, watchClaim } from './api';
import { applyEvent, initialLive, isTerminalError, type LiveState } from './live';
import type { ClaimEvent, ClaimState, Demo } from './types';

type Mode = 'preview' | 'live';
type Page = 'assessment' | 'upload' | 'sources';
interface Replay { input: ClaimState; state: ClaimState; events: ClaimEvent[] }
const policyURL = 'https://www.royalsundaram.in/assets/standalone-motor-own-damage-policy-private-car-rev2023.pdf';
const phaseLabels = { idle: 'Ready to begin', running: 'Assessment in progress', review: 'Ready for your review', escalated: 'Surveyor review required', done: 'Review completed', error: 'Assessment interrupted' };

export default function App() {
  const [mode, setMode] = useState<Mode>('preview');
  const [page, setPage] = useState<Page>('assessment');
  const [demos, setDemos] = useState<Demo[]>([]);
  const [selected, setSelected] = useState('clean_swift_front');
  const [activeDemo, setActiveDemo] = useState('');
  const [claim, setClaim] = useState<ClaimState | null>(null);
  const [events, setEvents] = useState<ClaimEvent[]>([]);
  const [live, setLive] = useState<LiveState>(initialLive);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [email, setEmail] = useState('');
  const [photoURLs, setPhotoURLs] = useState<string[]>([]);
  const [connection, setConnection] = useState('Preview ready');
  const [backendMock, setBackendMock] = useState(false);
  const cleanup = useRef<() => void>(() => {});
  const generation = useRef(0);
  const snapshotVersion = useRef(0);
  const localURLs = useRef<string[]>([]);
  const seen = useRef(new Set<string>());
  const stop = () => { cleanup.current(); cleanup.current = () => {}; };
  const clear = () => {
    stop(); generation.current++; seen.current.clear();
    localURLs.current.forEach(URL.revokeObjectURL); localURLs.current = []; setPhotoURLs([]);
    setClaim(null); setEvents([]); setLive(initialLive); setError(''); setNote(''); setEmail(''); setBusy(false); setActiveDemo('');
  };
  useEffect(() => {
    let active = true;
    const load = mode === 'preview' ? fetch('/demo/manifest.json').then(r => { if (!r.ok) throw new Error('Preview assets unavailable'); return r.json() as Promise<Demo[]>; }) : getDemos();
    load.then(items => { if (active) { setDemos(items); if (items.length) setSelected(items[0].name); } }).catch(e => { if (active) { setDemos([]); setError(e.message); } });
    setBackendMock(false);
    if (mode === 'live') request<{ mock?: boolean }>('/health').then(h => { if (active) setBackendMock(h.mock === true); }).catch(() => {});
    return () => { active = false; };
  }, [mode]);
  useEffect(() => () => { cleanup.current(); localURLs.current.forEach(URL.revokeObjectURL); generation.current++; }, []);

  const receive = (event: ClaimEvent) => {
    const key = JSON.stringify(event);
    if (seen.current.has(key)) return false;
    seen.current.add(key);
    setEvents(old => [...old.slice(-199), event]);
    setLive(old => applyEvent(old, event));
    if (event.type === 'error') setError(event.text);
    return true;
  };
  async function refresh(id: string, token: number) {
    const version = ++snapshotVersion.current;
    const state = await getClaim(id);
    if (token === generation.current && version === snapshotVersion.current) setClaim(state);
  }
  function connect(id: string, token: number) {
    stop(); setConnection('Connecting…');
    cleanup.current = watchClaim(id, event => {
      if (token !== generation.current) return;
      if (!receive(event)) return;
      if (['agent_end', 'send_back', 'interrupt', 'escalate', 'done', 'error'].includes(event.type)) {
        void refresh(id, token).catch(e => { if (token === generation.current) setError(e.message); });
      }
      if (['interrupt', 'escalate', 'done'].includes(event.type) || isTerminalError(event)) { stop(); setConnection('Assessment paused or complete'); }
    }, message => { if (token === generation.current) setConnection(message); }, () => { if (token === generation.current) setConnection('Live updates connected'); });
  }
  async function runDemo() {
    clear(); const token = generation.current; setBusy(true); setPage('assessment');
    try {
      if (mode === 'preview') {
        const response = await fetch(`/demo/${encodeURIComponent(selected)}.json`);
        if (!response.ok) throw new Error('Preview fixture could not be loaded.');
        const replay: Replay = await response.json();
        if (token !== generation.current) return;
        setActiveDemo(selected); setClaim({ ...replay.input, photos: replay.state.photos }); setConnection('Playing synthetic events');
        let index = 0;
        const timer = window.setInterval(() => {
          if (token !== generation.current) return;
          const event = replay.events[index++]; receive(event);
          if (event.type === 'agent_end') {
            setClaim(old => old && ({ ...old,
              ...(event.agent === 'damage' ? { damages: replay.state.damages } : {}),
              ...(event.agent === 'policy' ? { coverage: replay.state.coverage } : {}),
              ...(event.agent === 'cost' ? { estimate: replay.state.estimate } : {}),
            }));
          }
          if (event.type === 'send_back') setClaim(old => old && ({ ...old, retries: Number(event.data.retries) }));
          if (index >= replay.events.length) { window.clearInterval(timer); setClaim(replay.state); setConnection('Synthetic replay complete'); }
        }, 420);
        cleanup.current = () => window.clearInterval(timer);
      } else {
        const result = await request<{ claim_id: string }>(`/demo/${encodeURIComponent(selected)}`, { method: 'POST' });
        if (token !== generation.current) return;
        connect(result.claim_id, token); await refresh(result.claim_id, token);
      }
    } catch (e) { if (token === generation.current) setError((e as Error).message); }
    finally { if (token === generation.current) setBusy(false); }
  }
  async function upload(form: FormData, files: File[]) {
    clear(); const token = generation.current; setBusy(true);
    try {
      const result = await request<{ claim_id: string }>('/claims', { method: 'POST', body: form });
      if (token !== generation.current) return;
      localURLs.current = files.map(file => URL.createObjectURL(file)); setPhotoURLs(localURLs.current);
      setPage('assessment'); connect(result.claim_id, token); await refresh(result.claim_id, token);
    } catch (e) { if (token === generation.current) setError((e as Error).message); }
    finally { if (token === generation.current) setBusy(false); }
  }
  async function review(approved: boolean) {
    if (!claim || live.phase !== 'review' || claim.audit?.status !== 'pass' || busy) return;
    setBusy(true); setError(''); const token = generation.current;
    try {
      if (mode === 'preview') {
        setClaim({ ...claim, decision: approved ? 'approved' : 'rejected', outputs: approved ? { pdf_path: `/demo/${activeDemo}.pdf` } : {} });
        receive({ type: 'done', agent: 'finalize', ts: new Date().toISOString(), text: approved ? 'Preview approved. Synthetic report and email draft are ready.' : 'Preview rejected. No claim has been submitted.', data: {} });
      } else {
        // Subscribe before resuming so a fast finalization event is not missed.
        setLive(old => ({ ...old, phase: 'running' }));
        connect(claim.claim_id, token);
        await request(`/claims/${encodeURIComponent(claim.claim_id)}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved, note }) });
        if (token !== generation.current) return;
        await refresh(claim.claim_id, token);
      }
    } catch (e) { if (token === generation.current) { stop(); setLive(old => ({ ...old, phase: 'review' })); setError((e as Error).message); } }
    finally { if (token === generation.current) setBusy(false); }
  }
  async function showEmail() {
    setError('');
    if (mode === 'preview') {
      try { const r = await fetch(`/demo/${activeDemo}.txt`); if (!r.ok) throw new Error('Email draft unavailable'); setEmail(await r.text()); }
      catch (e) { setError((e as Error).message); }
    } else setEmail(claim?.outputs?.email_text || 'The backend has not produced an email draft yet.');
  }
  function changeMode(value: Mode) { clear(); setDemos([]); setMode(value); setConnection(value === 'preview' ? 'Preview ready' : 'Waiting for a claim'); }
  const totals = claim?.estimate?.totals;
  const canReview = live.phase === 'review' && claim?.audit?.status === 'pass' && !claim.decision;
  const isHandoff = !!claim?.escalation;
  const canDownload = (claim?.decision === 'approved' || isHandoff) && !!claim?.outputs?.pdf_path;
  const photoSrc = (index: number) => {
    const url = claim?.photos?.[index]?.url;
    if (mode === 'preview' && url?.startsWith('/demo/')) return url;
    if (photoURLs[index]) return photoURLs[index];
    // Do not interpret a backend filesystem path as a public URL.
    if (url?.startsWith('/api/') && !url.includes('..')) return url;
    return undefined;
  };

  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#" onClick={e => { e.preventDefault(); setPage('assessment'); }}><span className="brand-icon"><ShieldCheck size={26}/></span>ClaimMate<span className="brand-dot">.</span></a>
      <div className="workspace-label">CLAIMS WORKSPACE</div>
      <nav aria-label="Main navigation">
        <button className={page === 'assessment' ? 'nav active' : 'nav'} onClick={() => setPage('assessment')}><LayoutDashboard size={18}/>Assessment</button>
        <button className={page === 'upload' ? 'nav active' : 'nav'} onClick={() => setPage('upload')}><Plus size={18}/>New claim</button>
        <button className={page === 'sources' ? 'nav active' : 'nav'} onClick={() => setPage('sources')}><BookOpen size={18}/>Data & sources</button>
      </nav>
      <div className="sidebar-note"><ShieldCheck size={22}/><strong>Every decision,<br/>a little more clarity.</strong><p>Evidence-led assessment.<br/>You stay in control.</p></div>
      <div className="team"><span className="avatar">DD</span><div><strong>Dent Detectives</strong><small>AgentOps 2026 · HX-B7Y5</small></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div>Workspace <ChevronRight size={14}/> <strong>{page === 'assessment' ? 'Claim assessment' : page === 'upload' ? 'New claim' : 'Data & sources'}</strong></div><div className="mode-control"><span className={`connection-dot ${mode}`}/><label htmlFor="mode">Mode</label><select id="mode" value={mode} onChange={e => changeMode(e.target.value as Mode)}><option value="preview">Synthetic preview</option><option value="live">Live backend</option></select><span className="user-avatar">SK</span></div></header>
      <main><div className="page-heading"><div><span className="eyebrow">A CLEARER ROAD TO YOUR CLAIM</span><h1>{page === 'upload' ? 'Let’s start with the evidence.' : page === 'sources' ? 'Built on traceable sources.' : 'Every claim, explained.'}</h1><p>{page === 'upload' ? 'Add your photos and incident details. Our agents take it from here.' : page === 'sources' ? 'Know where the numbers come from, and where judgment is still needed.' : 'From damage evidence to a transparent estimate. Follow every step.'}</p></div>{page !== 'upload' && <button className="primary" onClick={() => setPage('upload')}><Plus size={17}/>New claim</button>}</div>
      {mode === 'preview' && <div className="preview-banner"><span><FlaskIcon/>Synthetic preview · Scripted events and test diagrams. No model assessment or insurer submission.</span><button onClick={() => changeMode('live')}>Connect backend <ArrowRight size={14}/></button></div>}
      {mode === 'live' && backendMock && <div className="preview-banner"><span><FlaskIcon/>Backend mock mode (LLM_MOCK=1) · Agents return canned demo answers. Tools, rules and audit logic run for real; this is not model inference.</span></div>}
      {error && <div className="error-banner" role="alert"><AlertTriangle size={18}/>{redact(error, claim)}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}
      {page === 'upload' && <UploadForm disabled={mode !== 'live' || busy} busy={busy} mock={mode === 'live' && backendMock} onSubmit={upload} />}
      {page === 'sources' && <Sources />}
      {page === 'assessment' && <>
        <section className="demo-bar"><div><span className="small-icon"><Network size={18}/></span><div><strong>Explore a claim</strong><small>{demos.find(d => d.name === selected)?.description || 'Select a scenario to get started'}</small></div></div><div className="demo-actions"><select aria-label="Demo scenario" value={selected} onChange={e => setSelected(e.target.value)} disabled={busy || live.phase === 'running'}>{demos.map(d => <option key={d.name} value={d.name}>{d.title || title(d.name)}</option>)}</select><button className="secondary" disabled={busy || !demos.length || live.phase === 'running'} onClick={runDemo}><RefreshCw size={15}/>{claim ? 'Run again' : 'Run demo'}</button>{live.phase === 'running' && <button className="text-button" onClick={() => { clear(); setConnection('Stopped viewing updates'); }}>Stop viewing</button>}</div></section>
        <div className="metrics"><div className="metric"><span className="metric-icon"><Car size={21}/></span><div><small>VEHICLE</small><strong>{claim ? `${claim.vehicle.make} ${claim.vehicle.model}` : 'Your vehicle'}</strong><span>{claim ? `${mask(claim.vehicle.reg_no)} · ${claim.vehicle.age_months} months old` : 'Select a demo or upload a claim'}</span></div></div><div className="metric"><span className="metric-icon mint"><ShieldCheck size={21}/></span><div><small>ASSESSMENT STATUS</small><strong>{claim?.decision === 'rejected' ? 'Claim rejected' : phaseLabels[live.phase]}</strong><span>{claim ? `${claim.claim_id} · ${claim.accident_date}` : 'Human review before finalization'}</span></div></div><div className="metric"><span className="metric-icon peach"><FileText size={21}/></span><div><small>ESTIMATED PAYABLE</small><strong>{totals ? `${money(totals.payable_low)} – ${money(totals.payable_high)}` : 'Awaiting assessment'}</strong><span>Indicative range · subject to policy review</span></div></div></div>
        <section className="panel graph-panel"><div className="panel-heading"><div><h2>The assessment, in motion <span className="live-badge"><Radio size={12}/>{mode === 'preview' ? 'PREVIEW' : backendMock ? 'LIVE · MOCK LLM' : 'LIVE'}</span></h2><p>Specialist agents. Independent checks. One traceable decision.</p></div><span className="retry-pill">Re-checks <strong>{live.retries} / 2</strong></span></div><AgentGraph live={live}/><div className="graph-footer"><span><i className="legend complete"/>Complete <i className="legend running"/>In progress <i className="legend review"/>Needs review</span><small>{connection} · Drag graph to explore</small>{mode === 'live' && claim && <button className="text-button" onClick={() => { setError(''); connect(claim.claim_id, generation.current); void refresh(claim.claim_id, generation.current).catch(e => setError(e.message)); }}>Reconnect</button>}</div></section>
        <div className="assessment-grid"><section className="panel"><div className="panel-heading"><div><h2>Photo evidence <span className="count">{claim?.photos?.length || 0}</span></h2><p>Every estimate starts with something you can see.</p></div><Camera size={20}/></div><div className="evidence-grid">{claim?.photos?.length ? claim.photos.map((photo, index) => <article className="evidence" id={`evidence-${photo.id}`} key={photo.id}>{photoSrc(index) ? <img src={photoSrc(index)} alt={`${claim.synthetic ? 'Synthetic test diagram' : 'Uploaded damage evidence'} ${index+1}`}/> : <div className="photo-placeholder"><Camera size={28}/><span>Photo URL unavailable</span></div>}<div className="evidence-info"><strong>Evidence {index+1}</strong><span className="tag">{claim.synthetic ? 'Synthetic fixture' : 'Uploaded photo'}</span><div className="tags">{claim.damages?.filter(d => d.photo_ids.includes(photo.id)).map(d => <span className="damage-tag" key={d.part}>{title(d.part)} · {d.severity} · {Math.round(d.confidence*100)}%</span>)}</div><small>{photo.exif_datetime ? `Capture: ${photo.exif_datetime.replace('T', ' ')}` : 'Capture date missing — supporting evidence required'}</small>{photo.duplicate_of && <span className="warning-text">Duplicate match: {photo.duplicate_of}</span>}</div></article>) : <div className="empty-state"><Camera size={32}/><strong>Evidence belongs here</strong><p>Run a demo or start a new claim to review photos and damage tags.</p></div>}</div>{claim && <div className="story"><span className="eyebrow">THE INCIDENT</span><p>“{redact(claim.story, claim)}”</p></div>}</section>
          <section className="panel audit-panel"><div className="panel-heading"><div><h2><ShieldCheck size={19}/>The independent audit</h2><p>Checks that keep the assessment honest.</p></div></div><div className="audit-checks">{['Photo date & policy period', 'Duplicate photo detection', 'Registration plate match', 'Story & damage consistency', 'Evidence & coverage for every line', 'Confidence & structural severity'].map((label, index) => { const finding = claim?.audit?.findings.find(f => f.check === `A${index+1}`); return <div className={`audit-row ${finding?.ok === false ? 'flagged' : ''}`} key={label}><span className={`audit-icon ${finding?.ok === true ? 'pass' : finding ? 'warn' : ''}`}>{finding?.ok === true ? <Check size={14}/> : finding ? <AlertTriangle size={14}/> : <Clock3 size={14}/>}</span><div><strong>{label}</strong><small>{finding ? redact(finding.detail, claim) : 'Waiting for the Auditor'}</small></div><span className="check-code">A{index+1}</span></div>; })}</div><div className={`audit-summary ${live.phase === 'escalated' ? 'escalated' : ''}`}>{live.phase === 'escalated' ? <><AlertTriangle size={18}/><span><strong>A surveyor needs to take a look.</strong>Approval is unavailable until the flagged evidence is resolved.</span></> : <><ShieldCheck size={18}/><span>No silent decisions. You review the assessment before a claim file is prepared.</span></>}</div></section></div>
        <section className="panel payout-panel"><div className="panel-heading"><div><h2>Your estimate, line by line</h2><p>Source-linked prices. Fixed depreciation. A policy reference for every row.</p></div><span className="tag">INR · ESTIMATE</span></div>{claim?.estimate?.lines.length ? <><div className="table-scroll"><table><thead><tr><th>PART & ACTION</th><th>PARTS PRICE</th><th>LABOUR RANGE</th><th>DEPRECIATION</th><th>PAYABLE RANGE</th><th>POLICY & EVIDENCE</th></tr></thead><tbody>{claim.estimate.lines.map((line, index) => <tr key={`${line.part}-${index}`}><td><strong>{title(line.part)}</strong><small>{title(line.action)} · {line.material}</small><details><summary>Assumptions & fitment</summary><p>{redact(line.note, claim)}</p>{line.paint > 0 && <p>Paint bill: {money(line.paint)}</p>}</details></td><td>{money(line.part_price)}{safeLink(line.part_source_url) && <a href={safeLink(line.part_source_url)} target="_blank" rel="noreferrer">Price source <ArrowUpRight size={11}/></a>}</td><td>{money(line.labour_low)} – {money(line.labour_high)}<small>Assumed labour</small></td><td>{Math.round(line.dep_pct*100)}%<small>{money(line.dep_amount)}</small></td><td className="payable">{money(line.payable_low)} – {money(line.payable_high)}</td><td><details><summary>{line.clause_id || 'Citation missing'}</summary><p>{redact(claim.coverage?.find(c => c.part === line.part)?.clause_quote || claim.coverage?.find(c => c.part === line.part)?.reason || 'Policy excerpt not available', claim)}</p><a href={policyURL} target="_blank" rel="noreferrer">Policy wording <ArrowUpRight size={11}/></a></details>{line.photo_ids.map(id => <a key={id} href={`#evidence-${id}`}>{id}</a>)}</td></tr>)}</tbody></table></div>{claim.coverage?.filter(c => c.status !== 'covered').map(c => <div className="exclusion" key={c.part}><AlertTriangle size={17}/><span><strong>{title(c.part)} · {title(c.status)}</strong>{redact(c.reason, claim)} <a href={policyURL} target="_blank" rel="noreferrer">{c.clause_id}</a></span></div>)}<div className="totals"><div><span>Gross repair estimate</span><strong>{money(totals?.gross_low)} – {money(totals?.gross_high)}</strong></div><div><span>Depreciation</span><strong>− {money(totals?.depreciation)}</strong></div><div><span>Claim deductible</span><strong>− {money(totals?.deductible)}</strong></div><div className="total-payable"><span>Estimated payable</span><strong>{money(totals?.payable_low)} – {money(totals?.payable_high)}</strong></div></div><p className="table-footnote">Line amounts are before the claim deductible. Prices depend on model and variant; labour is assumed. Final cover and settlement remain subject to insurer review.</p></> : <div className="empty-state compact"><FileText size={28}/><p>The Cost Estimator will add a sourced breakdown here.</p></div>}</section>
        <div className="bottom-grid"><section className="panel"><div className="panel-heading"><div><h2>Activity trail</h2><p>Follow the reasoning and the re-checks.</p></div><span className="count">{events.length}</span></div><ol className="timeline" aria-live="polite" aria-relevant="additions">{events.length ? events.slice().reverse().map((e, i) => <li key={`${e.ts}-${i}`} className={e.type === 'send_back' || e.type === 'escalate' ? 'attention' : ''}><span className="timeline-dot"/><div><strong>{title(e.agent)} <small>{e.type.replaceAll('_', ' ')}</small></strong><p>{redact(e.text, claim)}</p></div><time>{new Date(e.ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time></li>) : <p className="muted">Your assessment’s activity will appear here.</p>}</ol></section>
          <section className="panel review-panel"><div className="panel-heading"><div><h2>You have the final say.</h2><p>Review the evidence, coverage and estimate.</p></div><span className="small-icon mint"><CheckCircle2 size={22}/></span></div><div className="review-body"><label htmlFor="review-note">Review note <span>(optional)</span></label><textarea id="review-note" placeholder="Add a note for the claim file…" value={note} onChange={e => setNote(e.target.value)} disabled={!canReview || busy}/><div className="review-actions"><button className="primary" disabled={!canReview || busy} onClick={() => review(true)}><Check size={16}/>{busy ? 'Working…' : 'Approve estimate'}</button><button className="secondary" disabled={!canReview || busy} onClick={() => review(false)}>Reject</button></div><small className="muted">{claim?.decision ? `Decision: ${claim.decision}. ${mode === 'preview' ? 'This was a synthetic preview.' : 'Check the activity trail for finalization.'}` : live.phase === 'escalated' ? 'A surveyor must resolve the flagged evidence before approval. The hand-off file and email for the surveyor are ready below.' : 'Approval becomes available after the audit passes and human review is requested.'}</small><div className="outputs">{canDownload ? <a className="output-link" href={mode === 'preview' ? `/demo/${activeDemo}.pdf` : `${API}/claims/${encodeURIComponent(claim!.claim_id)}/pdf`} download><Download size={18}/>{mode === 'preview' ? 'Download sample PDF' : isHandoff ? 'Download surveyor hand-off PDF' : 'Download claim PDF'}<ArrowRight size={16}/></a> : <span className="output-link disabled"><Download size={18}/>Claim PDF available after approval</span>}<button className="output-link" disabled={!canDownload} onClick={showEmail}><Mail size={18}/>View insurer email draft<ArrowRight size={16}/></button></div></div></section></div>
      </>}
      <footer className="page-footer"><span><ShieldCheck size={14}/>ClaimMate · Evidence first. Human reviewed.</span><span>Team Dent Detectives · AgentOps 2026</span></footer>
      </main>
    </div>
    {email && <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="email-title"><div className="panel-heading"><h2 id="email-title">Insurer email · draft only</h2><button className="icon-button" aria-label="Close email draft" autoFocus onClick={() => setEmail('')}><X size={20}/></button></div><pre>{redact(email, claim)}</pre><p className="muted">Nothing has been sent. Supply full identifiers through the insurer’s secure channel.</p><button className="secondary" onClick={() => { const url = URL.createObjectURL(new Blob([redact(email, claim)], { type: 'text/plain' })); const a = document.createElement('a'); a.href = url; a.download = 'claim-email-draft.txt'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}><Download size={16}/>Download draft</button></section></div>}
  </div>;
}
function FlaskIcon() { return <span className="preview-symbol">◇</span>; }

function UploadForm({ disabled, busy, mock, onSubmit }: { disabled: boolean; busy: boolean; mock: boolean; onSubmit: (form: FormData, files: File[]) => Promise<void> }) {
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState('');
  function select(list: FileList | null) {
    const chosen = Array.from(list || []);
    if (chosen.length > 10 || chosen.some(f => !['image/jpeg', 'image/png', 'image/webp'].includes(f.type) || f.size > 8*1024*1024)) { setError('Choose up to 10 JPEG, PNG or WebP photos, each under 8 MB.'); return; }
    setFiles(chosen); setError('');
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('');
    const values = new FormData(event.currentTarget);
    const field = (key: string) => String(values.get(key) || '');
    const accident = field('accident_date'), reg = field('reg_date'), start = field('start'), end = field('end');
    if (!files.length) return setError('Add at least one damage photo.');
    if (end < start || reg > accident) return setError('Check the policy dates and registration date.');
    const a = new Date(accident), r = new Date(reg);
    const age_months = (a.getUTCFullYear()-r.getUTCFullYear())*12 + a.getUTCMonth()-r.getUTCMonth() - (a.getUTCDate()<r.getUTCDate() ? 1 : 0);
    const body = new FormData(); files.forEach(f => body.append('photos[]', f));
    body.append('story', field('story')); body.append('accident_date', accident);
    body.append('vehicle', JSON.stringify({ make: 'Maruti Suzuki', model: field('model'), reg_no: field('reg_no').toUpperCase(), cc: Number(field('cc')), reg_date: reg, age_months }));
    body.append('policy', JSON.stringify({ policy_no: field('policy_no'), start, end, idv: Number(field('idv')), zero_dep: values.has('zero_dep'), voluntary_deductible: Number(field('voluntary_deductible')) }));
    await onSubmit(body, files);
  }
  return <form className="panel upload-form" onSubmit={submit}>
    <div className="panel-heading"><div><h2>New claim</h2><p>Photographs help classify damage. Prices come from a sourced catalogue.</p></div></div>
    {disabled && !busy && <div className="form-notice">Switch to Live backend mode to submit a new claim.</div>}
    {mock && <div className="form-notice" role="alert"><AlertTriangle size={16}/> The backend is in mock mode (LLM_MOCK=1). Uploaded photos are not analysed by any AI model, so the claim will escalate with “no damage detected”. Restart the backend with LLM_MOCK=0 and a valid OLLAMA_API_KEY to assess real photos.</div>}
    <fieldset disabled={disabled}><div className="upload-zone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!disabled) select(e.dataTransfer.files); }}><UploadCloud size={32}/><strong>Add damage photos</strong><p>Drop photos here or choose files · up to 10 images, 8 MB each</p><input aria-label="Damage photos" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e => select(e.target.files)}/></div>
    {files.length > 0 && <div className="file-list">{files.map((file, i) => <span key={`${file.name}-${i}`}><Camera size={14}/>{file.name}<button type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles(old => old.filter((_, index) => i !== index))}><X size={13}/></button></span>)}</div>}
    <label>What happened?<textarea name="story" required maxLength={2000} placeholder="Describe the incident, where the vehicle was hit, and the damage you noticed."/></label>
    <div className="form-grid"><label>Accident date<input type="date" name="accident_date" required/></label><label>Vehicle model<select name="model"><option>Swift</option><option>Baleno</option></select></label><label>Registration number<input name="reg_no" required maxLength={20} placeholder="As shown on your RC"/></label><label>Registration date<input type="date" name="reg_date" required/></label><label>Engine capacity (cc)<input type="number" name="cc" min="1" max="10000" step="1" defaultValue={1197} required/></label><label>Policy number<input name="policy_no" required maxLength={80}/></label><label>Policy start<input type="date" name="start" required/></label><label>Policy end<input type="date" name="end" required/></label><label>Insured declared value (₹)<input type="number" name="idv" min="50000" step="1000" placeholder="e.g. 450000 (see policy schedule)" required/></label><label>Voluntary deductible (₹)<input type="number" name="voluntary_deductible" min="0" step="1" defaultValue={0} required/></label></div>
    <label className="checkbox"><input type="checkbox" name="zero_dep"/>My policy includes applicable zero-depreciation cover</label>
    <p className="muted">Policy and registration numbers are masked in the assessment and report. Photos may be processed by the backend’s vision provider.</p>
    {error && <div role="alert" className="error-banner">{error}</div>}<button className="primary" type="submit" disabled={disabled}>{busy ? 'Uploading…' : 'Start assessment'}<ArrowRight size={17}/></button></fieldset>
  </form>;
}
function Sources() {
  return <div className="sources-grid">{[
    ['Policy & depreciation', 'Royal Sundaram · Stand-Alone Motor Own Damage, Rev 2023', 'Fixed replacement-part rates, age bands and painting rules. The source PDF download is currently blocked by the insurer’s server; a local copy must be supplied for backend policy ingestion.', policyURL],
    ['Genuine parts catalogue', 'Maruti Suzuki Genuine Parts · checked 24 October 2026', '21 catalogue rows for Swift and Baleno. Each row carries a price, part number, source URL and fitment note. These are selected demo variants, not a universal VIN-matched catalogue.', 'https://www.marutisuzuki.com/genuine-parts'],
    ['Compulsory deductible', 'ICICI Lombard · Motor insurance FAQs', '₹1,000 for vehicles up to 1,500 cc; ₹2,000 above 1,500 cc. Voluntary deductible is added at claim level. Confirm the actual policy schedule.', 'https://www.icicilombard.com/info-center/faqs'],
    ['Labour & demonstration data', 'Explicit assumptions · synthetic fixtures', 'Labour ranges are engineering assumptions, not market quotes. Ten controlled test claims and three UI replays check behaviour. They are not measured vision accuracy.', ''],
  ].map(([heading, source, text, url]) => <section className="panel source-card" key={heading}><BookOpen size={24}/><h2>{heading}</h2><strong>{source}</strong><p>{text}</p>{url && <a href={url} target="_blank" rel="noreferrer">View source <ArrowUpRight size={15}/></a>}</section>)}</div>;
}
