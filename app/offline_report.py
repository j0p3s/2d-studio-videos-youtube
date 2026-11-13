"""Rebuilt, local-only HTML summary for a scene-checker run. No remote assets."""
from datetime import datetime, timezone
import hashlib
from html import escape
from pathlib import Path
import shutil
from urllib.parse import quote


DECISIONS = {
    'accepted_by_runtime_and_pixel_checks': 'Repair cleared technical checks; review the preview',
    'reverted_no_measured_improvement': 'Repair rejected; original restored',
    'repair_failed': 'Repair failed; original kept',
    'manual_scene_preserved': 'Approved scene preserved',
    'review_required': 'Needs review; repair mode was off',
}


def _image(source, project, folder, key, index):
    source = Path(source).resolve()
    allowed = (Path(project) / 'build/scene_audit').resolve()
    try:
        source.relative_to(allowed)
    except ValueError:
        return None
    if source.suffix.lower() not in ('.png', '.jpg', '.jpeg') or not source.is_file():
        return None
    target = folder / 'assets' / (key + '-' + str(index) + source.suffix.lower())
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return 'assets/' + quote(target.name)


def write_report(folder, records, *, started, finished=False, error=None, repair=False, export=False):
    """Replace both report entry points atomically; show only this run's records."""
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    def h(value):
        return escape(str(value), quote=True)
    total_scenes = sum(len((r.get('audit') or {}).get('shots', [])) for r in records)
    flagged = sum(bool(s.get('issues')) for r in records for s in (r.get('audit') or {}).get('shots', []))
    failed = sum(r.get('status') in ('failed', 'cancelled') for r in records)
    title = ('Check stopped' if error or failed else 'Review needed' if flagged else
             'Checks finished' if finished and records else 'No projects found' if finished else 'Checking scenes')
    color = 'bad' if error or failed else 'warn' if flagged else 'good'
    stamp = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        stamp = stamp.astimezone(ZoneInfo('Europe/Lisbon'))
        zone = 'Lisbon'
    except (ImportError, KeyError):
        zone = 'UTC'
    cards = []
    for record in records:
        audit = record.get('audit') or {}
        shots = audit.get('shots', [])
        errors = [s for s in shots if s.get('missing') or s.get('runtime_errors')]
        issues = [s for s in shots if s.get('issues')]
        state = ('Failed' if record.get('status') == 'failed' else 'Cancelled' if record.get('status') == 'cancelled'
                 else 'Checking' if record.get('status') == 'checking' else 'Needs review' if issues
                 else 'Technical checks clear · visual review required' if shots else 'No scene results')
        tone = 'bad' if record.get('error') else 'warn' if issues else 'good'
        details = []
        decisions = {}
        for item in audit.get('decisions', []):
            decisions.setdefault(item['id'], []).append(item)
        for scene in shots:
            sid = scene['id']
            warnings = ''.join('<li>' + h(x) + '</li>' for x in scene.get('issues', []))
            warnings = '<ul class="issues">' + warnings + '</ul>' if warnings else '<p class="muted">No detected technical defects. Acting, prop contact and narrative relevance still require visual review.</p>'
            changes = ''.join('<p class="decision">' + h(DECISIONS.get(d['status'], d['status'])) +
                              (': ' + h(d['detail']) if d.get('detail') else '') + '</p>' for d in decisions.get(sid, []))
            key = hashlib.sha256((str(record['path']) + sid).encode()).hexdigest()[:18]
            images = []
            for i, source in enumerate(scene.get('images', [])):
                try:
                    image = _image(source, record['path'], folder, key, i)
                except OSError:
                    image = None
                if image:
                    times = scene.get('sample_times', [])
                    caption = f'{times[i]:.2f}s' if i < len(times) else f'Sample {i+1}'
                    url = h(image + '?run=' + str(started))
                    images.append(f'<figure><a href="{url}" target="_blank" rel="noopener"><img src="{url}" loading="lazy" alt="{h(sid)} at {h(caption)}"></a><figcaption>{h(caption)}</figcaption></figure>')
            metrics = f"{scene.get('frames_checked', '—')} frames checked · Motion {scene.get('motion_ratio', '—')} · Detail {scene.get('color_spread', '—')}"
            details.append(f'<details open><summary><span>{h(sid)}</span><span class="badge warn">{"Needs repair / review" if scene.get("issues") else "Visual review required"}</span></summary><p class="muted">{h(metrics)}</p>{warnings}{changes}<div class="filmstrip">{"".join(images)}</div></details>')
        message = '<pre class="error">' + h(record['error']) + '</pre>' if record.get('error') else ''
        if not shots:
            message += '<p class="muted">No current scene details are available. Earlier audit results were not substituted for this run.</p>'
        frames = sum(s.get('frames_checked', 0) for s in shots)
        cards.append(f'<section class="project"><header><div><h2>{h(record["name"])}</h2><p class="path">{h(record["path"])}</p></div><span class="badge {tone}">{h(state)}</span></header><p class="muted">{len(shots)} scenes · {frames:,} frames · {len(issues)} flagged · {len(errors)} runtime failures</p>{message}{"".join(details)}</section>')
    fatal = '<pre class="error">' + h(error) + '</pre>' if error else ''
    empty = '<section class="project"><h2>No offline projects found</h2><p>Automatic discovery needs a <code>build/local_animation.json</code> checkpoint. Test folders starting with an underscore are excluded. You can also check a project explicitly with <code>--project projects/name</code>.</p></section>' if finished and not records and not error else ''
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-store"><title>Offline animation check report</title>
<style>
:root{{color-scheme:dark;font:15px/1.6 system-ui,sans-serif;background:#0a1319;color:#e9f3f1}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1200px;margin:auto;padding:40px 24px 70px}}h1{{font-size:clamp(28px,4vw,44px);line-height:1.12;margin:12px 0}}h2{{font-size:21px;margin:0;overflow-wrap:anywhere}}.eyebrow{{color:#60ddbd;letter-spacing:.13em;text-transform:uppercase;font-size:12px;font-weight:800}}.muted,.path,figcaption{{color:#9cb3bb}}.path{{font-size:12px;overflow-wrap:anywhere}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0}}.stat,.project,.note{{border:1px solid #29404b;background:#111f28;border-radius:16px;padding:22px}}.stat b{{display:block;font-size:30px;line-height:1.2}}.stat span{{color:#9cb3bb;font-size:12px}}.project{{margin:22px 0}}header{{display:flex;justify-content:space-between;align-items:start;gap:18px}}.badge{{display:inline-block;padding:4px 12px;border-radius:99px;font-size:12px;font-weight:750;white-space:nowrap}}.good{{background:#153c35;color:#70e6c2}}.warn{{background:#41351f;color:#ffd083}}.bad{{background:#482c30;color:#ffb1ac}}details{{border-top:1px solid #29404b;padding:16px 0}}summary{{cursor:pointer;display:flex;justify-content:space-between;gap:15px;font-weight:750}}.filmstrip{{display:flex;gap:10px;overflow-x:auto;padding:12px 0}}figure{{margin:0;flex:0 0 128px}}img{{width:128px;max-height:235px;object-fit:contain;display:block;border-radius:8px;background:#091117}}figcaption{{font-size:12px;text-align:center;padding:5px}}.issues{{color:#ffd083;padding-left:20px}}.error{{white-space:pre-wrap;overflow-wrap:anywhere;color:#ffb1ac;background:#24191f;padding:16px;border-radius:10px;font:13px/1.6 ui-monospace,monospace}}.decision{{color:#bce2d5}}.note{{background:#142b30;margin:24px 0}}code{{font-size:.9em;color:#b9dfd8}}a{{color:#72dfc3}}footer{{color:#9cb3bb;font-size:12px;margin-top:30px}}@media(max-width:650px){{.stats{{grid-template-columns:repeat(2,1fr)}}header{{display:block}}main{{padding:24px 14px}}.project{{padding:16px}}}}
</style></head><body><main>
<div class="eyebrow">2D Animation Studio · local report</div><h1>Offline animation checks</h1>
<span class="badge {color}">{h(title)}</span><p class="muted">Updated {h(stamp.strftime('%d %b %Y, %H:%M:%S'))} ({zone}). Rebuilt each launcher or CLI run.</p>
<div class="stats"><div class="stat"><b>{len(records)}</b><span>Projects</span></div><div class="stat"><b>{total_scenes}</b><span>Scenes checked</span></div><div class="stat"><b>{flagged}</b><span>Scenes flagged</span></div><div class="stat"><b>{failed}</b><span>Projects stopped</span></div></div>
<div class="note"><b>What this result means</b><p>Checks cover every frame for runtime errors, malformed rig joints, shared-pose mutation, invalid drawing coordinates and accidentally connected circles, plus sampled motion and detail. Technical clearance does not establish good acting, prop contact, narrative relevance or visual quality. Review the previews and finished video.</p><p>Repairs: <b>{'enabled' if repair else 'off (audit only)'}</b> · Video export: <b>{'requested' if export else 'not requested; existing MP4s are unchanged'}</b>. Rejected repairs restore the original code. Approved scenes are protected.</p></div>
{fatal}{empty}{''.join(cards)}<footer>Motion measures residual pixel changes; detail measures color spread. Report entry points: index.html and .index.html. No external scripts, fonts or network assets.</footer>
</main></body></html>'''
    for name in ('index.html', '.index.html'):
        target = folder / name
        temp = target.with_suffix('.tmp')
        temp.write_text(html, encoding='utf-8')
        temp.replace(target)
    return folder / '.index.html'
