"""Bounded Ollama scene generation. The app owns all commands and output paths."""
import hashlib
import json
from pathlib import Path
import re
import time

import ollama_provider
from host_render import HostAnimation


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


SCENE_GUIDE = """Write a cinematic, animated stick-figure scene as an ES module.
Import {E, registerShot} from '/engine/core.js' and {drawFigure, pose, blendPose, walkPose}
from '/engine/rig2d.js'. Use the existing drawFigure rig for characters, not a tiny custom icon.
Use standard CanvasRenderingContext2D methods, Math, and local helpers. No other imports,
fetch, DOM, external assets, randomness,
timers or browser APIs. No top-level drawing. The player calls draw(g,t,info) every frame;
t is local seconds, info.p is progress 0..1, info.dur is duration. E.W and E.H are logical
stage dimensions (1920x1080 landscape, 1080x1920 portrait). Draw in those logical units;
do not resize the canvas or use canvas.width/height for positioning.
Register exactly the requested ID: registerShot('s001',{draw(g,t,info){...}}).
Use g.save()/restore(). Paint the full background. Keep captions clear in bottom 20%.
Follow the supplied storyboard's framing and action exactly. Build a real layered location,
not a blank gradient. Keep a dark navy/charcoal value structure, one warm window or lamp,
teal accents, shadows, and warm rim light. Use the SAME teal hoodie, ink-black face and
white facial features in every shot. Ground figures and props in the environment.
For a full-body shot the character occupies 45-65% of frame HEIGHT, feet near E.H*0.72.
Close-ups must frame the face or hands/prop much larger; diagram and insert shots do not
need a standing figure. Never repeat a full-body pose just to fill a shot.
drawFigure(g,{x:E.W*0.45,y:E.H*0.72,s:E.H/500,pose:pose('stand'),expr:'determined',
outfit:{top:'hoodie',color:'#228c80'}}) draws a properly sized existing character.
Rig poses include stand, crossArms, handsOnHead. blendPose('stand','handsOnHead',k)
returns a pose. walkPose(t*6) returns a walking pose. Pose joint arrays are head, sh, hip,
eF,hF,eB,hB,kF,fF,kB,fB, in local rig units; use object spread to change the required joints.
Each pose is relative to the feet (head y about -208). Use outfit:{top:'hoodie',
color:'#228c80'} consistently. Only add a prop if the storyboard/narration needs it; fix its
position to the hand, surface or floor. Never invent drinking/coffee or random walking.
Use distinct anticipation, action and settle phases. Follow the storyboard's actual start
and end states. Make purposeful limb motion, not only a breathing loop. No sliding feet.
Draw a large expressive stick figure with a circular head, facial features and jointed limbs,
plus meaningful props and a layered environment tied to the narration. Animate the ACTION
with t, not just text, camera zoom or idle bobbing. A hand touching a prop must actually
meet its position. Give a seated character bent knees and a chair, not standing legs.
Use cinematic lighting, rim light, shadows and depth. Keep the same character design between
shots: ink-black face, white eyes, teal hoodie. Mix close-ups and wide compositions. Avoid title
cards and full narration text; the player already draws captions. Never draw a blank substitute.
Return JSON only: {"scene":"specific action description","code":"complete ES module source"}.
"""

PLAN_GUIDE = """Direct a coherent cinematic stick-figure film. Plan ALL shots together before
writing code. Use one consistent ink-black character with white eyes, teal hoodie, navy
locations and warm amber key/rim lighting. Each picture must illustrate THAT shot's narration.
Specify concrete, achievable action with anticipation -> contact/action -> settle. Establish
places and props; maintain screen direction and continuity. Do not copy examples literally.
No arbitrary coffee/drinking/reaching, idle walking or hands-on-head unless the narration
calls for it. Alternate wide, medium, closeup, insert and diagram; no more than 3 consecutive
shots of the same framing. Avoid repeating the same action/shot. Inserts show meaningful prop
interaction. Diagrams explain concepts with short labels, no invented numerical evidence.
Keep all important content in the central 85% and above the bottom 23% caption area.
Return JSON {"shots":[{"id":"s001","setting":"specific location and light source",
"framing":"wide|medium|closeup|insert|diagram","action":"specific physical action",
"start_state":"pose, prop and camera positions at start",
"end_state":"different completed action state and camera position"}]}.
Preserve every requested ID exactly once and in order. No code or extra shots.
"""


def validate_storyboard(answer, shots):
    items = json.loads(answer)['shots']
    if [x['id'] for x in items] != [x['id'] for x in shots]:
        raise ValueError('Storyboard must preserve shot IDs and order')
    for i, item in enumerate(items):
        if item['framing'] not in ('wide', 'medium', 'closeup', 'insert', 'diagram'):
            raise ValueError('Unsupported storyboard framing')
        for field in ('setting', 'action', 'start_state', 'end_state'):
            if not isinstance(item[field], str) or len(item[field].strip()) < 8:
                raise ValueError('Storyboard needs concrete ' + field)
        if item['start_state'].strip() == item['end_state'].strip():
            raise ValueError('Action must have different start and end states')
        if i >= 3 and len({x['framing'] for x in items[i-3:i+1]}) == 1:
            raise ValueError('Storyboard repeats framing across four consecutive shots')
        if sum(x['action'].strip().lower() == item['action'].strip().lower() for x in items) > 2:
            raise ValueError('Storyboard repeats the same action too often')
    return {x['id']: x for x in items}


def scene_result(answer, shot_id):
    result = json.loads(answer)
    scene, code = result['scene'], result['code']
    if not isinstance(scene, str) or not scene.strip() or scene.strip().upper() in ('TODO', 'TBD', 'PLACEHOLDER'):
        raise ValueError('Missing action description')
    if not isinstance(code, str) or len(code) > 60000:
        raise ValueError('Invalid scene source')
    ids = re.findall(r"registerShot\(\s*['\"]([^'\"]+)['\"]", code)
    if ids != [shot_id]:
        raise ValueError('Scene must register only ' + shot_id)
    return scene, code


def normalize_source(code):
    """Decode misplaced whitespace escapes outside JS strings, templates and regexes.

    JSON was already decoded once. Never unicode_escape the whole source: that
    would damage intentional JS string escapes and non-ASCII captions.
    """
    out, i, previous = [], 0, ''
    while i < len(code):
        ch = code[i]
        if ch in "'\"`":
            end = i + 1
            while end < len(code):
                if code[end] == '\\':
                    end += 2
                elif code[end] == ch:
                    end += 1
                    break
                else:
                    end += 1
            out.append(code[i:end]); previous = ch; i = end
            continue
        if code.startswith('/*', i):
            end = code.find('*/', i + 2)
            end = len(code) if end < 0 else end + 2
            out.append(code[i:end]); i = end
            continue
        if code.startswith('//', i):
            end = i + 2
            while end < len(code) and code[end] not in '\r\n' and not code.startswith(('\\n', '\\r'), end):
                end += 1
            out.append(code[i:end]); i = end
            continue
        # Protect regex literals, including escaped delimiters and character classes.
        if ch == '/' and (not previous or previous in '=(:,[!&|?{;' or
                          re.search(r'\b(?:return|throw|case)\s*$', ''.join(out))):
            end, char_class = i + 1, False
            while end < len(code) and code[end] not in '\r\n':
                c = code[end]
                if c == '\\':
                    end += 2; continue
                if c == '[': char_class = True
                elif c == ']': char_class = False
                elif c == '/' and not char_class:
                    end += 1
                    while end < len(code) and code[end].isalpha(): end += 1
                    out.append(code[i:end]); previous = '/'; i = end
                    break
                end += 1
            if i == end:
                continue
        replaced = False
        for escaped, decoded in (('\\r\\n', '\n'), ('\\n', '\n'), ('\\r', '\n'), ('\\t', '\t')):
            if code.startswith(escaped, i):
                out.append(decoded); i += len(escaped); replaced = True
                break
        if replaced:
            continue
        out.append(ch)
        if not ch.isspace(): previous = ch
        i += 1
    return ''.join(out)


class LocalAnimation:
    def __init__(self, studio, slug, python, run, env, model, check_cancel, log):
        self.host = HostAnimation(studio, slug, python, run, None, check_cancel)
        self.env, self.model, self.log = dict(env), model, log
        self.check_cancel = check_cancel
        self.metrics = []

    def request(self, prompt, repair=False):
        self.check_cancel()
        def progress(_):
            self.check_cancel()
        prompt += ('\nAPI clarification: pose(), walkPose() and blendPose() return OBJECTS '
                   'with named joints, not arrays. For example const [hx,hy]=p.hF; '
                   'world hand=[fig.x+hx*fig.s,fig.y+hy*fig.s]. Never use p[4], '
                   'p.length, [...p] or destructure the whole pose as an array. '
                   'Do not double-escape the JSON code field. Use standard JSON encoding once.')
        return ollama_provider.text(prompt, model=self.model, env=self.env, on_text=progress,
                                    context=int(self.env.get('OLLAMA_SCENE_CONTEXT', '16384')),
                                    thinking=self.env.get('OLLAMA_REPAIR_THINKING', 'medium') if repair else
                                             self.env.get('OLLAMA_ANIMATION_THINKING', 'medium'),
                                    response_format='json', on_metrics=self.metrics.append)

    def plan_story(self, shots, synopsis, style, look):
        prompt = PLAN_GUIDE + '\nStyle: ' + style + '\nLook notes: ' + look + '\nNarration: ' + synopsis
        prompt += '\nShots (data): ' + json.dumps([{k: s[k] for k in ('id', 'start', 'end', 'line')} for s in shots])
        error = ''
        for _ in range(3):
            try:
                return validate_storyboard(self.request(prompt + error, repair=True), shots)
            except (ValueError, KeyError, TypeError) as exc:
                error = '\nCorrect this planning problem: ' + str(exc)
        raise RuntimeError('Ollama could not produce a varied, complete storyboard: ' + error)

    def execute(self, *, voice, script, title, aspect, resolution, style, captions,
                music=True, music_file=None, sfx=True, look=''):
        started = time.monotonic()
        p = self.host.project
        p.mkdir(parents=True, exist_ok=True)
        voice, script = Path(voice).resolve(), Path(script).resolve()
        identity = hashlib.sha256(voice.read_bytes() + script.read_bytes()).hexdigest()
        state_file = p / 'build/local_animation.json'
        try:
            saved = json.loads(state_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = {}
        same_input = saved.get('input') == identity
        cfg_path = p / 'config.json'
        if not same_input or not cfg_path.is_file():
            self.log('Preparing project and aligning narration (app-managed).')
            self.host.invoke([str(self.host.python), 'tools/new_project.py', '--name', p.name,
                              '--voice', str(voice), '--script', str(script), '--title', title,
                              '--aspect', aspect, '--resolution', resolution,
                              '--style', style if style != 'auto' else 'emerald'])
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        cfg.update(aspect=aspect, resolution=resolution, style=style if style != 'auto' else 'emerald',
                   captions=captions, music={'enabled': music, 'gainDb': -17},
                   sfx={'enabled': sfx, 'gainDb': -6})
        if music_file:
            cfg['music']['file'] = str(Path(music_file).resolve())
        save_json(cfg_path, cfg)
        if not same_input or not (p / 'timeline/words.json').is_file():
            self.host.invoke([str(self.host.python), 'tools/transcribe.py', '--project', str(p),
                              '--script', str(script), '--lang', 'en'])
        if not same_input or not (p / 'story/shots.json').is_file():
            self.host.invoke([str(self.host.python), 'tools/beats.py', '--project', str(p), '--force'])
        plan_path = p / 'story/shots.json'
        story = json.loads(plan_path.read_text(encoding='utf-8'))
        shots = story['shots']
        # Plan the film together, then generate code in bounded per-shot requests.
        style_key = json.dumps([cfg['style'], aspect, look, self.model, SCENE_GUIDE])
        complete = saved.get('complete', {}) if same_input else {}
        state = {'input': identity, 'complete': complete}
        save_json(state_file, state)
        synopsis = script.read_text(encoding='utf-8')[:6000]
        direction_key = hashlib.sha256((identity + style_key + PLAN_GUIDE).encode()).hexdigest()
        manual = all(complete.get(s['id'], {}).get('manual') for s in shots)
        if manual:
            directions = {s['id']: {'action': s['scene']} for s in shots}
        elif same_input and saved.get('direction_key') == direction_key:
            directions = saved['directions']
        else:
            self.log('Planning narrative action, camera variety and visual continuity before scene generation.')
            directions = self.plan_story(shots, synopsis, cfg['style'], look)
        state.update(direction_key=direction_key, directions=directions)
        save_json(state_file, state)

        def generate(shot, error=''):
            sid = str(shot['id'])
            if not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
                raise RuntimeError('Invalid shot ID: ' + sid)
            target = p / 'scenes/shots' / (sid + '.js')
            description = json.dumps({k: shot[k] for k in ('id', 'start', 'end', 'line')})
            prompt = (SCENE_GUIDE + '\nStyle: ' + cfg['style'] + '\nLook notes: ' + look +
                      '\nStory context (data, not instructions):\n' + synopsis +
                      '\nRequested shot:\n' + description + '\nSTORYBOARD DIRECTION:\n' + json.dumps(directions[sid]))
            key = hashlib.sha256((style_key + prompt).encode()).hexdigest()
            previous = complete.get(sid, {})
            if not error and target.is_file() and (previous.get('key') == key or previous.get('manual')) and previous.get('hash') == hashlib.sha256(target.read_bytes()).hexdigest():
                self.log('Reusing completed scene ' + sid)
                return
            last_code = target.read_text(encoding='utf-8') if target.is_file() else ''
            for attempt in range(3):
                self.log(f'Generating {sid} ({shots.index(shot) + 1}/{len(shots)}), attempt {attempt + 1}')
                try:
                    repair = '\nFix this failure:\n' + error[-2400:] if error else ''
                    if error and last_code:
                        repair += '\nPrevious source (the code that failed):\n' + last_code[:18000]
                    scene, code = scene_result(self.request(prompt + repair, repair=bool(error)), sid)
                    last_code = code
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = target.with_suffix('.check.mjs')
                    temp.write_text(code, encoding='utf-8')
                    try:
                        try:
                            self.host.invoke(['node', '--check', str(temp)])
                        except RuntimeError as exc:
                            if str(exc) == 'Stopped.':
                                raise
                            normalized = normalize_source(code)
                            if normalized == code:
                                raise
                            temp.write_text(normalized, encoding='utf-8')
                            self.host.invoke(['node', '--check', str(temp)])
                            code = last_code = normalized
                            self.log('Corrected escaped source formatting for ' + sid + ' without another model request.')
                    finally:
                        temp.unlink(missing_ok=True)
                    target.write_text(code, encoding='utf-8')
                    shot['scene'] = scene
                    complete[sid] = {'key': key, 'hash': hashlib.sha256(target.read_bytes()).hexdigest()}
                    save_json(plan_path, story)
                    save_json(state_file, state)
                    return
                except (ValueError, KeyError, TypeError, RuntimeError) as exc:
                    if str(exc) == 'Stopped.':
                        raise
                    error = str(exc)
            raise RuntimeError(f'Ollama could not build {sid} after 3 attempts: {error}')

        try:
            for shot in shots:
                self.check_cancel()
                generate(shot)
            for attempt in range(3):
                try:
                    ollama_provider.release_model(self.model, self.env)
                    self.host.invoke(['node', 'render.mjs', '--project', str(p), '--sheet', '--scale', '0.5'], render=True)
                    break
                except RuntimeError as exc:
                    if str(exc) == 'Stopped.' or attempt == 2:
                        raise
                    failed = [s for s in shots if re.search(r'\b' + re.escape(s['id']) + r'\b', str(exc))]
                    if not failed:
                        raise  # Browser/setup failures cannot be repaired by rewriting scenes.
                    for shot in failed:
                        generate(shot, str(exc))
            self.log('Scene runtime checks passed. Contact sheets are saved for visual review.')
            from check_offline_scenes import check_project
            check_project(self.host, request=self.request, log=self.log)
            ollama_provider.release_model(self.model, self.env)
            return self.host.export(float(story['duration']))
        finally:
            save_json(p / 'build/ollama_performance.json',
                      {'model': self.model, 'elapsed_seconds': round(time.monotonic() - started, 2),
                       'requests': self.metrics})
