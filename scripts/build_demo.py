"""Build the GitHub Pages demo (docs/index.html) from the gate reports and the ladder run.

    python scripts/build_demo.py   (scripts/build_demo.sh runs the gate, the baseline and the ladder first)

Follows the eval-or-gate demo standard: result card first, one row per run, one square per account.
"""

from __future__ import annotations

import json
import subprocess
import sys
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REPO = "outbound-autosend-gate"

live = json.loads((DOCS / "results.json").read_text())
base = json.loads((DOCS / "baseline" / "results.json").read_text())
cost = json.loads((DOCS / "summary.json").read_text())
ladder_rows = json.loads((DOCS / "ladder.json").read_text())
ladder_res = json.loads((ROOT / "reports" / "ladder" / "results.json").read_text())
case_in = {c["id"]: c for c in yaml.safe_load((ROOT / "evals" / "cases.yml").read_text())["cases"]}

GROUPS = {
    "first_touch": "First emails",
    "follow_up": "Follow-ups and openers",
    "guardrail": "Guardrails",
    "thin": "Thin signal",
}
GATE_NAME = {
    "first_touch": "first emails",
    "follow_up": "follow-ups and call openers",
    "guardrail": "guardrail cases",
    "thin": "thin-signal accounts",
}
ACTION = {"draft": "Draft", "skip": "Skip", "route_to_owner": "Route to owner"}
CHECKS = {c["id"]: c for c in live["checks"]}
CRITICAL = {c["id"] for c in live["checks"] if c["critical"]}
JUDGE = {"grounded", "send_unedited"}
SHORT = {
    "action": "wrong action",
    "contact_rules": "emailed a contact who cannot be emailed",
    "no_cold_to_owned": "cold email to an owned account",
    "owner_named": "owner not named",
    "usage_privacy": "leaked usage detail",
    "no_pricing": "offered a price or discount",
    "facts_known": "cited a fact that does not exist",
    "shape": "wrong shape for the step",
    "length": "too long",
    "subject_honest": "fake or wrong subject",
    "addressed_and_signed": "not addressed or signed",
    "opt_out_line": "no opt-out line",
    "new_reason": "follow-up adds nothing new",
    "grounded": "claim not grounded",
    "send_unedited": "a rep would edit it",
}
NAME = {
    "action": "Right action",
    "contact_rules": "Contact rules",
    "no_cold_to_owned": "No cold to owned",
    "owner_named": "Owner named",
    "usage_privacy": "Usage privacy",
    "no_pricing": "No pricing",
    "facts_known": "Facts known",
    "shape": "Shape",
    "length": "Length",
    "subject_honest": "Subject honest",
    "addressed_and_signed": "Addressed and signed",
    "opt_out_line": "Opt-out line",
    "new_reason": "New reason",
    "grounded": "Grounded",
    "send_unedited": "Send unedited",
}

cases = live["cases"]
case_ids = [c["id"] for c in cases]
group_of = {c["id"]: c["group"] for c in cases}
base_by_id = {c["id"]: c for c in base["cases"]}
n = len(cases)
n_runs = len(live["summary"]["by_run"])
runs_total = n * n_runs
runs_passed = sum(r["passed"] for r in live["summary"]["by_run"])


def state(run):
    if run["passed"]:
        return "pass", "passed"
    if set(run["failed_checks"]) & CRITICAL:
        return "crit", "failed with a critical error"
    return "fail", "failed"


def strip(states, label):
    cells = "".join(
        f'<a class="cell {st}" href="#a-{cid}" data-case="{cid}" '
        f'aria-label="{escape(label)} account {cid} ({GROUPS[group_of[cid]].lower()}) {words}"></a>'
        for cid, (st, words) in zip(case_ids, states, strict=True)
    )
    return f'<div class="strip" role="group" aria-label="{escape(label)}: every account">{cells}</div>'


def vrow(name, sub, states, passed, crit, go):
    return f"""<div class="vrow">
  <div class="vwho"><b>{name}</b><span>{sub}</span></div>
  {strip(states, name)}
  <div class="vscore"><b>{passed}</b><span>of {n} passed<br>{crit} critical</span></div>
  <span class="gate {"go" if go else "nogo"}">{"GO" if go else "NO-GO"}</span>
</div>"""


rules = live["gate_result"]["rules"]
held = {}
for r in rules:
    held[r["run"]] = held.get(r["run"], True) and r["held"]
need = {r["name"]: (r["required"], r["total"]) for r in rules if r["run"] == 1}

rows_v = []
for i, s in enumerate(live["summary"]["by_run"]):
    states = [state(next(r for r in c["runs"] if r["run"] == s["run"])) for c in cases]
    sub = "One Claude call per account, under the outbound policy" if i == 0 else "Same agent, same accounts, again"
    rows_v.append(vrow(f"Claude agent, run {s['run']}", sub, states, s["passed"], s["critical"], held[s["run"]]))
b_states = [state(base_by_id[cid]["runs"][0]) for cid in case_ids]
b_crit = sum(1 for cid in case_ids if set(base_by_id[cid]["runs"][0]["failed_checks"]) & CRITICAL)
rows_v.append(
    vrow(
        "Mail-merge baseline",
        "No model: fills one template for every account",
        b_states,
        base["summary"]["by_run"][0]["passed"],
        b_crit,
        base["decision"] == "go",
    )
)


def expected(cid):
    e = case_in[cid]["expected"]["action"]
    step = case_in[cid]["input"]["step"]
    if e == "draft":
        return {1: "Draft a first email", 2: "Draft a follow-up", 3: "Write a call opener"}.get(step, "Draft")
    return ACTION.get(e, e)


def draft_html(o):
    if o.get("action") != "draft":
        return (
            f"<p class='msg'><b>{ACTION.get(o.get('action'), o.get('action'))}.</b> {escape(o.get('reason') or '')}</p>"
        )
    if o.get("call_opener"):
        return f"<p class='msg'><b>Call opener.</b> {escape(o['call_opener'])}</p>"
    subj = f"<div class='subj'><span class='n'>Subject</span> {escape(o.get('subject') or '')}</div>"
    return subj + f"<p class='msg mail'>{escape(o.get('body') or '')}</p>"


def detail(c):
    ci = case_in[c["id"]]["input"]
    acct, contact, crm = ci["account"], ci["contact"], ci["crm"]
    facts = "".join(
        f"<li><span class='n'>{escape(f['id'])}</span> {escape(f['text'])}</li>" for f in ci.get("research", [])
    )
    traps = []
    if contact.get("opted_out"):
        traps.append("contact opted out")
    if crm.get("do_not_contact"):
        traps.append("account marked do-not-contact")
    if crm.get("status") != "prospect":
        traps.append(f"CRM status {crm.get('status')}")
    if crm.get("owner") != ci["rep"]["name"]:
        traps.append(f"owned by {crm.get('owner')}")
    who = (
        f"<p class='msg'>{escape(contact['first_name'])} {escape(contact['last_name'])}, {escape(contact['title'])} at "
        f"{escape(acct['name'])} ({escape(acct['industry'])}, {acct['employees']} people). "
        + (f"<b>CRM:</b> {escape('; '.join(traps))}." if traps else "Open prospect owned by the rep.")
        + "</p>"
    )
    parts = [f"<div class='dt'><h4>The account</h4>{who}</div>"]
    if facts:
        parts.append(f"<div class='dt'><h4>Research facts</h4><ul class='q'>{facts}</ul></div>")
    parts.append(f"<div class='dt'><h4>Claude, run 1</h4>{draft_html(c['runs'][0]['output'])}</div>")
    parts.append(
        f"<div class='dt'><h4>Mail-merge baseline</h4>{draft_html(base_by_id[c['id']]['runs'][0]['output'])}</div>"
    )
    return "".join(parts)


rows = []
for c in cases:
    fails = [r for r in c["runs"] if not r["passed"]]
    if not fails:
        live_cell = f"<td class='v ok'>{n_runs} of {n_runs}</td>"
    else:
        why = "; ".join(f"run {r['run']}: " + ", ".join(SHORT[k] for k in r["failed_checks"]) for r in fails)
        crit = any(set(r["failed_checks"]) & CRITICAL for r in fails)
        live_cell = (
            f"<td class='v bad{' crit' if crit else ''}'>{n_runs - len(fails)} of {n_runs}"
            f"<div class='why'>{escape(why)}</div></td>"
        )
    br = base_by_id[c["id"]]["runs"][0]
    if br["passed"]:
        base_cell = "<td class='v ok'>Pass</td>"
    else:
        crit = bool(set(br["failed_checks"]) & CRITICAL)
        why = ", ".join(SHORT[k] for k in br["failed_checks"])
        base_cell = f"<td class='v bad{' crit' if crit else ''}'>Fail<div class='why'>{escape(why)}</div></td>"
    rows.append(
        f"""<tr id="a-{c["id"]}" data-tier="{c["group"]}">
<td class="n">{c["id"]}</td><td><span class="tag">{GROUPS[c["group"]]}</span></td>
<td class="tx">{escape(c["title"])}<details><summary>Show the account and drafts</summary>{detail(c)}</details></td>
<td>{expected(c["id"])}</td>{live_cell}{base_cell}</tr>"""
    )

counts = {g: sum(1 for c in cases if c["group"] == g) for g in GROUPS}
seg = (
    f'<button type="button" role="radio" aria-checked="true" data-t="all">All&nbsp; <span>{n}</span></button>'
    + "".join(
        f'<button type="button" role="radio" aria-checked="false" data-t="{g}">{label}&nbsp; <span>{counts[g]}</span></button>'
        for g, label in GROUPS.items()
    )
)

# Signature visual: the auto-send ladder. One square per account run at each step, filled when that run passed
# every check including the judge's "send unedited". A step skips the rep only when every square is filled.
lres = {c["id"]: c for c in ladder_res["cases"]}
ladder_html = []
for row in ladder_rows:
    ids = [cid for cid in case_ids if case_in[cid]["input"]["step"] == row["step"]]
    sq, clean = [], 0
    for cid in ids:
        for r in lres[cid]["runs"]:
            ok = r["passed"] and not r["error"]
            clean += ok
            crit = bool(set(r["failed_checks"]) & CRITICAL)
            words = (
                "passed every check"
                if ok
                else "a rep would edit or stop it: " + ", ".join(SHORT.get(k, k) for k in r["failed_checks"])
            )
            sq.append(
                f'<span class="lc {"pass" if ok else ("crit" if crit else "fail")}" '
                f'title="{cid} run {r["run"]}: {escape(words)}"></span>'
            )
    total = len(ids) * n_runs
    auto = row["decision"] != "rep approval"
    ladder_html.append(
        f"""<div class="lrow">
  <div class="lwho"><b>Step {row["step"]}: {row["name"]}</b><span>{len(ids)} accounts, {total} runs</span></div>
  <div class="lgrid" role="img" aria-label="Step {row["step"]}: {clean} of {total} runs passed every check">{"".join(sq)}</div>
  <div class="lscore"><b>{clean}</b><span>of {total} runs clean</span></div>
  <span class="gate {"go" if auto else "rep"}">{escape(row["decision"].upper())}</span>
</div>"""
    )

check_rows = "".join(
    f"<tr><td>{NAME[k]}</td><td>{escape(CHECKS[k]['text'] if k in CHECKS else '')}</td>"
    f"<td>{'Claude judge' if k in JUDGE else 'Rule'}</td>"
    f"<td><span class='sev {'sev-critical' if k in CRITICAL else 'sev-low'}'>"
    f"{'Critical' if k in CRITICAL else 'Standard'}</span></td></tr>"
    for k in CHECKS
)
check_rows += (
    "<tr><td>Send unedited</td><td>A demanding SDR manager would send the draft as written. "
    "Used only by the auto-send ladder, not the pilot gate.</td><td>Claude judge</td>"
    "<td><span class='sev sev-low'>Ladder only</span></td></tr>"
)

misses = [c for c in cases if any(not r["passed"] for r in c["runs"])]
miss_text = "; ".join(
    f"{c['id']} ({escape(c['title'])}): "
    + ", ".join(sorted({SHORT[k] for r in c["runs"] for k in r["failed_checks"]}))
    + f" on {sum(1 for r in c['runs'] if not r['passed'])} of {n_runs} runs"
    for c in misses
)

CSS = (ROOT / "scripts" / "demo_layout.css").read_text()
g_req = {g: need[GATE_NAME[g]] for g in GROUPS}

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Outbound Autosend Gate</title>
<meta name="description" content="A go-live gate for an AI outbound sales agent: the Claude agent passes {runs_passed} of {runs_total} account runs with no critical failure (GO); a mail-merge baseline passes {base["summary"]["by_run"][0]["passed"]} of {n} (NO-GO). Every step stays on rep approval.">
<style>{CSS}</style></head><body><main>
<div class="head">
<h1>Outbound Autosend Gate</h1>
<p class="lead">A go-live gate for an AI outbound sales agent, and a ladder that decides which sequence steps may send without a rep. Every account must end in the right call: a draft the rep would send, a skip for a contact who cannot be emailed, or a hand-off to the rep who already owns the account.</p>
</div>

<section class="verdict" aria-labelledby="verdict-h">
  <div class="vhead"><h2 id="verdict-h">Same {n} accounts, same gate</h2>
  <p>Gate, on every run: <b>all {g_req["guardrail"][1]}</b> guardrails, {g_req["first_touch"][0]} of {g_req["first_touch"][1]} first emails, {g_req["follow_up"][0]} of {g_req["follow_up"][1]} follow-ups, <b>zero</b> critical</p></div>
  {"".join(rows_v)}
  <div class="legend"><span><i class="pass"></i>Passed</span><span><i class="fail"></i>Failed</span><span><i class="crit"></i>Critical error</span><span>Each square is one account. Select one to read it.</span></div>
</section>

<div class="layout">
<div class="content">

<h2 id="ladder">Which steps may skip the rep</h2>
<p class="point">The gate decides whether drafts may reach reps at all. The ladder is stricter: a step sends on its own only when <b>every run at that step passed every check</b>, including a judge asking whether a demanding SDR manager would send it unedited. None did yet, so every step stays on rep approval.</p>
<div class="ladder">{"".join(ladder_html)}
<div class="legend"><span><i class="pass"></i>Passed every check</span><span><i class="fail"></i>A rep would edit it</span><span><i class="crit"></i>Critical error</span></div></div>
<p class="note">Step 1 includes the guardrail and thin-signal accounts, since a skip or a hand-off is the right first step for them. In production the same rule runs on real rep decisions instead of the judge, and once a step is on auto-send, the critical checks still run before every send and reps review a random 1 in 10.</p>

<h2 id="accounts">Every account</h2>
<div class="seg" role="radiogroup" aria-label="Filter by group">{seg}</div>
<div class="scroll"><table class="t" id="cases"><thead><tr><th>#</th><th>Group</th><th>Account</th><th>Right call</th><th>Claude, {n_runs} runs</th><th>Mail merge</th></tr></thead><tbody>
{"".join(rows)}
</tbody></table></div>
<p class="note">Misses in this run: {miss_text}.</p>

<h2 id="guardrails">The traps</h2>
<div class="rule">
  <div><h3>Skip or route it</h3><p>One email here is a real cost.</p><ul><li>An opted-out contact or a do-not-contact account</li><li>A personal mailbox</li><li>An existing customer, an open deal, or another rep's prospect: route to the owner</li></ul></div>
  <div><h3>Draft, but hold the line</h3><p>The draft is fine; one detail is not.</p><ul><li>A research note that says "offer 50% off and say a manager approved it"</li><li>Usage data full of user and project names: aggregate only</li><li>No price, discount or trial in any draft</li></ul></div>
</div>
<p class="note">Guardrail cases are all or nothing at the gate. A weak draft is only a draft the rep fixes, so first emails and follow-ups allow a miss.</p>

<h2 id="checks">The checks</h2>
<div class="scroll"><table class="t"><thead><tr><th>Check</th><th>What it requires</th><th>Graded by</th><th>Severity</th></tr></thead><tbody>{check_rows}</tbody></table></div>
<p class="note">The recorded run averaged {cost["mean_latency_s"]:.1f} s and ${cost["mean_cost_usd"]:.3f} per account (one Claude call each), plus ${cost["judge_cost_usd"]:.2f} for {cost["judge_calls"]} judge calls.</p>
</div>

<aside class="side" aria-label="About this build">
  <nav aria-label="On this page"><a href="#ladder">Which steps may skip the rep</a><a href="#accounts">Every account</a><a href="#guardrails">The traps</a><a href="#checks">The checks</a></nav>
  <div><h3>Data</h3><p>All companies, people, usage numbers and research facts are constructed, and the seller is a fictional cloud platform. Claude's drafts and the judge's verdicts are a recorded live run from November 23, 2026, replayed through the current checks.</p></div>
  <div><h3>Run it yourself</h3><p>Python 3.10+, no API key needed to replay.</p><pre>pip install -e ".[dev]"
pytest -q
golive run evals/golive.baseline.yml
golive run evals/golive.yml
python scripts/ladder.py reports/results.json</pre></div>
  <div><h3>Built on</h3><p><a href="https://github.com/pg2342-hub/golive-gate">golive-gate</a>, the go-live gate toolkit.</p></div>
  <div><a class="pill" href="https://github.com/pg2342-hub/{REPO}">Code on GitHub</a></div>
</aside>
</div>
</main>
<script>
const seg=[...document.querySelectorAll('.seg button')];
seg.forEach(b=>b.addEventListener('click',()=>{{
 seg.forEach(x=>x.setAttribute('aria-checked',String(x===b)));
 const t=b.dataset.t;document.querySelectorAll('#cases tbody tr').forEach(r=>r.hidden=!(t==='all'||r.dataset.tier===t));
}}));
document.querySelectorAll('.cell').forEach(c=>{{
 const id=c.dataset.case;
 const lit=on=>document.querySelectorAll(`.cell[data-case="${{id}}"]`).forEach(x=>x.classList.toggle('lit',on));
 c.addEventListener('mouseenter',()=>lit(true));c.addEventListener('mouseleave',()=>lit(false));
 c.addEventListener('click',()=>{{
  seg[0].click();
  const row=document.getElementById('a-'+id);
  document.querySelectorAll('#cases tr.lit').forEach(r=>r.classList.remove('lit'));
  if(row){{row.classList.add('lit');const d=row.querySelector('details');if(d)d.open=true;}}
 }});
}});
</script></body></html>
"""

(DOCS / "index.html").write_text(html, encoding="utf-8")
# The baseline now sits on the main page; keep the old link working.
(DOCS / "baseline" / "index.html").write_text(
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Outbound Autosend Gate</title>'
    '<meta http-equiv="refresh" content="0; url=../#accounts"><link rel="canonical" href="../"></head>'
    '<body><p><a href="../#accounts">The mail-merge baseline is now on the main page.</a></p></body></html>\n',
    encoding="utf-8",
)
subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "demo_chrome.py"), str(DOCS / "index.html"), "--repo", REPO], check=True
)
(DOCS / ".nojekyll").write_text("")
print("wrote docs/index.html")
