/* Shared study-session panel; phone is an honest, read-only snapshot. */
(function(host) {
  'use strict';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const id = () => crypto.randomUUID().replace(/-/g,'');
  const duration = sec => { sec = Math.max(0, Math.floor(sec)); return `${String(Math.floor(sec/3600)).padStart(2,'0')}:${String(Math.floor(sec/60)%60).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`; };
  const date = s => s ? new Date(s).toLocaleString([], {dateStyle:'medium',timeStyle:'medium'}) : 'In progress';
  const local = s => { const d = new Date(s); return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,19); };
  const views = new WeakMap(), timers = new Set();
  const prompt = s => `/study Continue Brain study session ${s.id}: ${s.course} — ${s.topic}. Read my Tutor Genome, tutor me with one question at a time, and save evidence from my attempts.`;
  function mount(root, data, send, options={}) {
    if (!root) return;
    let v = views.get(root);
    if (!v) { v = {root, busy:false, signature:'', data:null}; views.set(root,v); timers.add(v); }
    v.offset = Date.parse(data?.server_time || new Date().toISOString()) - Date.now();
    v.data = data || {sessions:[],genome:[],observations:[],revision:0}; v.send=send; v.options=options;
    const signature = JSON.stringify([v.data.sessions,v.data.genome,v.data.revision,options.readOnly]);
    if (v.signature === signature || v.busy) { tick(v); return; }
    const drafts = Object.fromEntries([...root.querySelectorAll('input,textarea,select')].map(el=>[el.name,el.value]));
    const open = [...root.querySelectorAll('details[open]')].map(el=>el.dataset.key);
    const focus = root.contains(document.activeElement) ? document.activeElement?.name : null;
    const a = v.data.active, sessions = [...v.data.sessions].reverse(), latest = a || sessions[0], readOnly=options.readOnly;
    v.signature = signature;
    root.classList.add('study-panel');
    root.innerHTML = `<p class="study-error" role="alert" hidden></p>
      ${readOnly ? '<p class="study-muted">Synced study history. Start, stop, and recover sessions on desktop Brain.</p>' : ''}
      ${a ? `<div class="study-active"><h3>${esc(a.course)} · ${esc(a.topic)}</h3><p class="study-timer" aria-label="Elapsed study time" data-study-timer></p><p class="study-muted">Started ${esc(date(a.started_at))}</p>
        ${a.interrupted ? `<div class="study-warning"><p>Was this session interrupted? The timer is held at the last check-in (${esc(date(a.last_seen))}).</p>${!readOnly ? '<div class="study-actions"><button data-action="continue">I kept studying — continue</button></div>' : ''}</div>` : ''}
        ${!readOnly ? `<form data-stop><label>${a.interrupted ? 'When did you finish?' : 'End time (optional; defaults to now)'}<input name="ended_at" type="datetime-local" step="1" ${a.interrupted ? `value="${local(a.last_seen)}" required` : ''}></label><button class="primary" type="submit">Stop session</button></form>` : ''}
        <p class="study-muted">${esc(a.discord?.message || '')}</p>
        ${!readOnly ? `<div class="study-actions"><button data-action="copy">Copy tutoring prompt</button>${['unavailable','pending','unverified'].includes(a.discord?.state) ? '<button data-action="discord_retry">Retry Discord DND</button>' : ''}</div><p class="study-muted">Paste the prompt into Claude Code to activate /study in that conversation.</p>` : ''}</div>` : !readOnly ? `<form data-start><div class="study-fields"><label>Course<input name="course" maxlength="300" placeholder="STAT 252" required></label><label>Topic<input name="topic" maxlength="300" placeholder="Conditional probability" required></label></div><button type="submit" class="primary">Start session</button><p class="study-muted">Starts a timer and attempts to set Discord to Do Not Disturb.</p></form>` : ''}
      <section class="study-history"><h3>Study sessions</h3><p class="study-muted">${sessions.filter(s=>s.ended_at).length} completed · ${duration(sessions.filter(s=>s.ended_at).reduce((sum,s)=>sum+s.duration_seconds,0))} total</p><div class="study-history-list">${sessions.length ? sessions.map(s=>`<details class="study-row" data-key="session-${s.id}"><summary><strong>${esc(s.course)} · ${esc(s.topic)}</strong> — ${s.ended_at ? duration(s.duration_seconds) : s.interrupted ? 'Needs review' : 'Running'}</summary><p>Started: ${esc(date(s.started_at))}<br>Ended: ${esc(date(s.ended_at))}</p><p class="study-muted">${esc(s.discord?.message || '')}</p>${s.ended_at && !readOnly ? `<form data-correct="${s.id}"><label>Correct end time<input name="correct-${s.id}" type="datetime-local" step="1" value="${local(s.ended_at)}" required></label><button type="submit">Save end time</button></form>` : ''}${s.discord?.state==='restore_failed' && !readOnly ? `<button data-retry="${s.id}">Retry restoring Discord</button>` : ''}</details>`).join('') : '<p class="study-muted">Your first study session will appear here.</p>'}</div></section>
      <section class="study-genome"><h3>Tutor Genome</h3><p class="study-muted">Topic observations grow from your work. Each assessment has evidence you can inspect or retract.</p>
        ${(v.data.genome||[]).map(n=>`<details class="study-node" data-key="node-${esc(n.course)}-${esc(n.topic)}"><summary><strong>${esc(n.course)} · ${esc(n.topic)}</strong> — ${esc(n.status)}</summary><p class="study-muted">${esc(n.confidence)} confidence · ${n.count} observations · Last observed ${esc(date(n.last_seen))}</p><ul class="study-evidence">${n.evidence.map(e=>`<li>${esc(e.outcome)} — ${esc(e.evidence)}<br><small>${esc(date(e.created_at))} · ${esc(e.source || 'Session '+e.session_id)}</small>${!readOnly ? `<br><button data-retract="${e.id}">Retract observation</button>` : ''}</li>`).join('')}</ul></details>`).join('') || '<p class="study-muted">No observations yet. The tutor records examples as you practice.</p>'}
        ${latest && !readOnly ? `<details data-key="add-evidence"><summary>Add an observation</summary><form data-observe><label>Study session<select name="session_id">${sessions.map(s=>`<option value="${s.id}">${esc(s.course)} · ${esc(s.topic)} · ${esc(date(s.started_at))}</option>`).join('')}</select></label><label>Concept<input name="concept" maxlength="300" required></label><label>What happened?<select name="outcome"><option value="independent">Solved independently</option><option value="hinted">Solved with hints</option><option value="struggled">Needs more practice</option></select></label><label>Evidence from your attempt<textarea name="evidence" maxlength="2000" required placeholder="Describe the problem and the reasoning demonstrated."></textarea></label><label>Source or question reference (optional)<input name="source" maxlength="500"></label><button type="submit">Save observation</button></form></details>` : ''}
      </section>`;
    for(const [name,value] of Object.entries(drafts)) { const el=[...root.querySelectorAll('input,textarea,select')].find(x=>x.name===name); if(el) el.value=value; }
    for(const el of root.querySelectorAll('details')) if(open.includes(el.dataset.key)) el.open=true;
    if(focus) [...root.querySelectorAll('input,textarea,select')].find(x=>x.name===focus)?.focus();
    root.onsubmit=async e=>{
      e.preventDefault(); const f=e.target, values=Object.fromEntries(new FormData(f));
      if(f.matches('[data-start]')) { const startKey=JSON.stringify([values.course,values.topic]); if(v.startKey!==startKey) {v.startId=id();v.startKey=startKey;} v.startId ||= id(); await act(v,{action:'start',id:v.startId,course:values.course,topic:values.topic}); if(v.data.active) v.startId=null; }
      if(f.matches('[data-stop]')) await act(v,{action:'stop',id:a.id,...(values.ended_at?{ended_at:new Date(values.ended_at).toISOString()}:{})});
      if(f.matches('[data-correct]')) await act(v,{action:'correct_end',id:f.dataset.correct,ended_at:new Date(values['correct-'+f.dataset.correct]).toISOString()});
      if(f.matches('[data-observe]')) { const ok=await act(v,{action:'observe',id:id(),session_id:values.session_id,topic:values.concept,outcome:values.outcome,evidence:values.evidence,source:values.source,revision:v.data.revision}); if(ok) { for(const name of ['evidence','concept','source']) root.querySelector(`[name="${name}"]`).value=''; } }
    };
    root.onclick=async e=>{
      const b=e.target.closest('button'); if(!b || readOnly) return;
      if(b.dataset.action==='copy') { try { await navigator.clipboard.writeText(prompt(a)); b.textContent='Copied'; } catch { showError(v,'Clipboard unavailable. Run /study in Claude Code and ask to continue your active Brain session.'); } }
      else if(b.dataset.action) await act(v,{action:b.dataset.action,id:a.id});
      else if(b.dataset.retract) await act(v,{action:'retract',id:b.dataset.retract,revision:v.data.revision});
      else if(b.dataset.retry) await act(v,{action:'discord_retry',id:b.dataset.retry});
    };
    tick(v);
  }
  function showError(v,text) { const el=v.root.querySelector('.study-error'); if(el) {el.textContent=text; el.hidden=false;} }
  async function act(v,body) {
    if(v.busy) return false; v.busy=true; v.root.setAttribute('aria-busy','true');
    v.root.querySelectorAll('button').forEach(b=>b.disabled=true);
    let error='',ok=false;
    try { const data=await v.send(body); if(data) v.data=data; ok=true; }
    catch(e) { error=e.message || 'Could not save your session. Try again.'; }
    finally {v.busy=false;v.signature='';v.root.setAttribute('aria-busy','false');mount(v.root,v.data,v.send,v.options);if(error)showError(v,error);}
    return ok;
  }
  function tick(v) {
    const el=v.root.querySelector('[data-study-timer]'), a=v.data?.active;
    if(el && a) {const elapsed=a.interrupted || v.options.readOnly ? a.duration_seconds : (Date.now()+v.offset-Date.parse(a.started_at))/1000; el.textContent=duration(elapsed);}
  }
  if(typeof document!=='undefined') setInterval(()=>{for(const v of timers) { if(!v.root.isConnected) {timers.delete(v);continue;} tick(v); }},1000);
  host.BrainStudy={mount,duration,prompt};
  if(typeof module!=='undefined')module.exports=host.BrainStudy;
})(typeof window==='undefined'?globalThis:window);
