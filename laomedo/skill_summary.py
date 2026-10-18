"""Conservative missing-description detection for host-owned authoring tasks."""
from pathlib import Path
import re


def has_description(text):
    """Preserve any nonempty or unfamiliar YAML value rather than overwrite it."""
    text = text.lstrip('\ufeff').replace('\r\n', '\n')
    front = re.match(r'\A---[ \t]*\n(.*?)\n---(?:\n|$)', text, re.S)
    if not front:
        return False
    lines = front[1].splitlines()
    for index, line in enumerate(lines):
        match = re.match(r'^description\s*:\s*(.*)$', line)
        if not match:
            continue
        value = match[1].strip()
        if value.startswith(('"', "'")):
            # Only an unambiguously empty quoted scalar is missing.
            return not bool(re.fullmatch(r'''(?:"\s*"|'\s*')\s*(?:#.*)?''', value))
        value = value.split(' #', 1)[0].strip()
        if value.startswith('#') or value == '':
            # YAML also permits a plain scalar beginning on the following line.
            for following in lines[index + 1:]:
                if following and not following[0].isspace():
                    break
                if following.strip() and not following.lstrip().startswith('#'):
                    return True
            return False
        if value in {'null', 'Null', 'NULL', '~'}:
            return False
        if re.fullmatch(r'[>|][1-9]?[+-]?', value):
            for following in lines[index + 1:]:
                if following and not following[0].isspace():
                    break
                if following.strip():
                    return True
            return False
        return True
    return False


def summary_authoring(snapshot):
    skill = next((f for f in snapshot['files'] if f['path'] == 'SKILL.md'), None)
    if not skill or not isinstance(skill.get('text'), str):
        raise ValueError('skill_summary_source_unavailable')
    if has_description(skill['text']):
        return {'summary_required': False, 'authoring_instructions': ''}
    instructions = (Path(__file__).parent / 'resources/skills/skill-summary/SKILL.md').read_text(encoding='utf-8')
    return {'summary_required': True, 'authoring_instructions': instructions}
