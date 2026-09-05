"""Mobalytics/GGG .build -> one PoB2 XML and URL-safe zlib/Base64 code.

Python 3.10+, standard library only. Source data is kept verbatim in the report.
"""
import argparse
import base64
import glob
import hashlib
import json
import re
import sys
import zlib
from pathlib import Path
import xml.etree.ElementTree as ET

def bundled_path(filename):
    """Locate a bundled resource when running from PyInstaller or source."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    return base / filename


DEFAULT_CATALOG = bundled_path('catalog-0_5.json')
MAX_INPUT = 16 * 1024 * 1024


class ConversionError(ValueError):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_INPUT:
        raise ValueError('Arquivo excede 16 MiB')
    return json.loads(raw.decode('utf-8-sig'))


def passive_map(data):
    if isinstance(data, dict) and 'passives' in data:
        data = data['passives']
    if isinstance(data, list):
        pairs = []
        for row in data:
            if not isinstance(row, dict) or 'Id' not in row or 'PassiveSkillsHash' not in row:
                raise ValueError('Mapa em lista exige Id e PassiveSkillsHash')
            pairs.append((row['Id'], row['PassiveSkillsHash']))
    elif isinstance(data, dict):
        pairs = list(data.items())
    else:
        raise ValueError('Formato de mapa JSON desconhecido')
    result = {}
    for key, value in pairs:
        if isinstance(value, dict):
            value = value.get('PassiveSkillsHash')
        if not isinstance(key, str) or not key or isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
            raise ValueError(f'Mapeamento inválido: {key!r} -> {value!r}')
        number = int(value)
        if not 0 <= number < 65536:
            raise ValueError(f'Hash fora de 0..65535: {key}')
        if key in result and result[key] != number:
            raise ValueError(f'Mapeamento ambíguo: {key}')
        result[key] = number
    if not result:
        raise ValueError('Mapa de passivas vazio')
    return result


def stage_key(name):
    text = name.casefold()
    m = re.search(r'\b(?:act|ato)\s*(\d+)\b', text)
    if m:
        rank = int(m[1]) * 10
    elif re.search(r'\binterlud', text):
        m = re.search(r'interlud\w*\s*(\d+)', text)
        rank = 50 + (int(m[1]) if m else 0)
    else:
        rank = next((r for token, r in [('early', 100), ('mid', 110), ('late', 120),
                                      ('high', 130), ('mirror', 140)] if re.search(r'\b' + token + r'\b', text)), 1000)
    natural = tuple((0, int(s)) if s.isdigit() else (1, s) for s in re.split(r'(\d+)', text))
    return rank, natural


def entry(value):
    if isinstance(value, str) and value:
        return {'id': value}
    if isinstance(value, dict) and isinstance(value.get('id'), str) and value['id']:
        return value
    raise ValueError('Entrada precisa de id textual não vazio')


def validate_source(data):
    if not isinstance(data, dict):
        raise ValueError('A raiz precisa ser um objeto JSON')
    for key in ('name', 'description', 'notes', 'ascendancy', 'author', 'link', 'class', 'tree_version'):
        if key in data and not isinstance(data[key], str):
            raise ValueError(f'{key} precisa ser texto')
    for key in ('passives', 'skills', 'inventory_slots'):
        if key in data and not isinstance(data[key], list):
            raise ValueError(f'{key} precisa ser uma lista')
    if not any(data.get(k) for k in ('passives', 'skills', 'inventory_slots', 'description', 'notes')):
        raise ValueError('Build vazia ou sem conteúdo reconhecido')
    for p in data.get('passives', []):
        p = entry(p)
        if type(p.get('weapon_set', 0)) is not int or p.get('weapon_set', 0) not in (0, 1, 2):
            raise ValueError('weapon_set precisa ser 0, 1 ou 2')
    for skill in data.get('skills', []):
        skill = entry(skill)
        if not isinstance(skill.get('support_skills', []), list):
            raise ValueError('support_skills precisa ser uma lista')
        for support in skill.get('support_skills', []):
            entry(support)
    for item in data.get('inventory_slots', []):
        if not isinstance(item, dict) or not isinstance(item.get('inventory_id'), str):
            raise ValueError('Item precisa de inventory_id')
        for k in ('slot_x', 'slot_y'):
            if type(item.get(k, 0)) is not int or item.get(k, 0) < 0:
                raise ValueError(f'{k} inválido')
    # Reject XML-invalid control characters anywhere, without silently deleting notes.
    def strings(obj):
        if isinstance(obj, str):
            if any(not (c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF) for c in obj):
                raise ValueError('Texto contém caracteres inválidos para XML 1.0')
        elif isinstance(obj, dict):
            for k, v in obj.items():
                strings(k)
                strings(v)
        elif isinstance(obj, list):
            for v in obj:
                strings(v)
    strings(data)


def resolve_class(data, catalog, fallback):
    class_name = data.get('class') or fallback
    asc = data.get('ascendancy', '')
    for cls in catalog['classes']:
        for i, a in enumerate(cls['ascendancies'], 1):
            if asc and asc in (a['internalId'], a['name']):
                if class_name and class_name.casefold() != cls['name'].casefold():
                    raise ValueError('Classe e ascendência incompatíveis')
                return cls, i, a
        if not asc and class_name and cls['name'].casefold() == class_name.casefold():
            return cls, 0, {'name': 'None', 'internalId': ''}
    raise ValueError(f'Classe/ascendência não identificada ({class_name!r}, {asc!r}); informe --class')


def encode(xml):
    return base64.urlsafe_b64encode(zlib.compress(xml, 9)).decode('ascii')


def decode(code):
    code = ''.join(code.split())
    raw = base64.b64decode(code + '=' * (-len(code) % 4), altchars=b'-_', validate=True)
    d = zlib.decompressobj()
    xml = d.decompress(raw, MAX_INPUT + 1)
    if len(xml) > MAX_INPUT or not d.eof or d.unused_data or d.unconsumed_tail:
        raise ValueError('Código truncado, grande demais ou com dados extras')
    return xml


def validate_roundtrip(xml, code, expected_stages=None):
    if decode(code) != xml:
        raise ValueError('Round-trip não preservou o XML')
    root = ET.fromstring(xml)
    if root.tag != 'PathOfBuilding':
        raise ValueError('Raiz XML inválida')
    specs, skills, items = [root.findall(p) for p in ('Tree/Spec', 'Skills/SkillSet', 'Items/ItemSet')]
    if not specs or len(specs) != len(skills) or len(specs) != len(items):
        raise ValueError('Quantidade de estágios inconsistente')
    if expected_stages is not None and len(specs) != expected_stages:
        raise ValueError('Quantidade de estágios inesperada')
    item_ids = {x.get('id') for x in root.findall('Items/Item')}
    if len(item_ids) != len(root.findall('Items/Item')):
        raise ValueError('IDs de item duplicados')
    for i, (tree, skill, item) in enumerate(zip(specs, skills, items), 1):
        if skill.get('id') != str(i) or item.get('id') != str(i):
            raise ValueError('IDs de conjuntos inconsistentes')
        if not tree.get('title') == skill.get('title') == item.get('title'):
            raise ValueError('Títulos de estágios inconsistentes')
        for slot in item.findall('Slot'):
            if slot.get('itemId') != '0' and slot.get('itemId') not in item_ids:
                raise ValueError('Referência a item inexistente')
    return root


def convert(paths, catalog_path=DEFAULT_CATALOG, map_path=None, tree_version=None,
            class_name=None, manual_order=False, allow_partial=False, title='Merged build'):
    catalog = read_json(catalog_path)
    version = tree_version or catalog['tree_version']
    if version != catalog['tree_version']:
        raise ConversionError('Versão da árvore difere do catálogo; gere um catálogo da versão desejada')
    mapping_data = read_json(map_path) if map_path else catalog
    if isinstance(mapping_data, dict) and mapping_data.get('tree_version', version) != version:
        raise ConversionError('Versão do mapa difere da árvore')
    mapping = passive_map(mapping_data)
    report = {'tree_version': version, 'catalog_source': catalog.get('source'),
              'catalog_commit': catalog.get('commit'), 'stages': [], 'skipped': [], 'warnings': []}
    stages = []
    seen = set()
    for path in paths:
        path = Path(path).resolve()
        if path in seen:
            continue
        seen.add(path)
        try:
            data = read_json(path)
            validate_source(data)
            # Explicit version metadata, when present, must agree.
            declared = data.get('tree_version')
            if declared and declared.replace('.', '_') != version:
                raise ValueError('Versão explícita da build difere do catálogo')
            filename_version = re.search(r'\[(\d+)\.(\d+)(?:\.\d+)?\]', path.stem)
            if filename_version and '_'.join(filename_version.groups()) != version:
                raise ValueError('Versão no nome do arquivo difere do catálogo')
            stages.append((path, data))
        except (OSError, ValueError, UnicodeError) as e:
            report['skipped'].append({'file': str(path), 'reason': str(e)})
    if not stages:
        raise ConversionError('Nenhuma build válida; nenhum PoB gerado', report)
    if not manual_order:
        stages.sort(key=lambda s: stage_key(s[0].stem))
    resolved = []
    try:
        # Ascendancy on later stages can identify the class of early stages.
        inferred = {resolve_class(d, catalog, class_name)[0]['name'] for _, d in stages if d.get('ascendancy') or d.get('class') or class_name}
        if len(inferred) > 1:
            raise ValueError('Arquivos de classes diferentes não podem formar uma única build')
        fallback = class_name or next(iter(inferred), None)
        resolved = [resolve_class(d, catalog, fallback) for _, d in stages]
    except ValueError as e:
        raise ConversionError(str(e), report) from e
    root = ET.Element('PathOfBuilding')
    ET.SubElement(root, 'Build', {'targetVersion': '0_1', 'className': resolved[0][0]['name'],
                                'ascendClassName': resolved[0][2]['name'], 'viewMode': 'TREE'})
    tree = ET.SubElement(root, 'Tree', activeSpec='1')
    skills = ET.SubElement(root, 'Skills', activeSkillSet='1')
    items = ET.SubElement(root, 'Items', activeItemSet='1', useSecondWeaponSet='false')
    notes = [title, 'Converted from .build files. Missing levels/quality remain unspecified; PoB applies its defaults.',
             'Inventory hints are notes, not rolled equipment. Original stage JSON follows for lossless reference.']
    titles = set()
    item_counter = 0
    unresolved = False
    for index, ((path, data), (cls, asc_id, asc)) in enumerate(zip(stages, resolved), 1):
        stage_title = path.stem
        suffix = 1
        while stage_title in titles:
            suffix += 1
            stage_title = f'{path.stem} ({suffix})'
        titles.add(stage_title)
        stage = {'file': str(path), 'title': stage_title, 'source': data, 'unmapped_passives': [],
                 'unmapped_gems': [], 'unmapped_slots': [], 'warnings': []}
        report['stages'].append(stage)
        spec = ET.SubElement(tree, 'Spec', {'title': stage_title, 'treeVersion': version,
            'classId': str(cls['integerId']), 'classInternalId': str(cls['integerId']),
            'ascendClassId': str(asc_id), 'ascendancyInternalId': asc['internalId'],
            'secondaryAscendClassId': '0', 'masteryEffects': ''})
        node_ids, weapons, node_notes = {}, {1: [], 2: []}, {}
        for p in data.get('passives', []):
            p = entry(p)
            node = mapping.get(p['id'])
            if node is None:
                stage['unmapped_passives'].append(p['id'])
                unresolved = True
                continue
            mode = p.get('weapon_set', 0)
            if node in node_ids and node_ids[node] != mode:
                raise ConversionError(f'{stage_title}: alocações conflitantes para {node}', report)
            node_ids[node] = mode
            if p.get('additional_text'):
                node_notes.setdefault(node, []).append(str(p['additional_text']))
        spec.set('nodes', ','.join(map(str, sorted(node_ids))))
        for node, mode in node_ids.items():
            if mode:
                weapons[mode].append(node)
        for mode, ids in weapons.items():
            if ids:
                ET.SubElement(spec, f'WeaponSet{mode}', nodes=','.join(map(str, sorted(ids))))
        if node_notes:
            n = ET.SubElement(spec, 'Notes')
            for node, texts in node_notes.items():
                ET.SubElement(n, 'Note', nodeId=str(node)).text = '\n'.join(texts)
        skillset = ET.SubElement(skills, 'SkillSet', id=str(index), title=stage_title)
        for raw in data.get('skills', []):
            skill = entry(raw)
            group = None
            for j, gem in enumerate([skill] + [entry(v) for v in skill.get('support_skills', [])]):
                known = catalog['gems'].get(gem['id'])
                if not known:
                    stage['unmapped_gems'].append(gem['id'])
                    unresolved = True
                    if j == 0:
                        break  # Never create a support-only group for an unknown main skill.
                    continue
                if group is None:
                    group = ET.SubElement(skillset, 'Skill', enabled='true', mainActiveSkill='1', label=known['nameSpec'])
                attrs = dict(known, gemId=gem['id'], enabled='true')
                if gem.get('additional_text'):
                    attrs['note'] = str(gem['additional_text'])
                # .build's level_interval is character availability, NOT gem level.
                for field, low, high in (('level', 1, 40), ('quality', 0, 100)):
                    if field in gem:
                        val = gem[field]
                        if type(val) is not int or not low <= val <= high:
                            raise ConversionError(f'{stage_title}: {field} inválido em {gem["id"]}', report)
                        attrs[field] = str(val)
                ET.SubElement(group, 'Gem', attrs)
        itemset = ET.SubElement(items, 'ItemSet', id=str(index), title=stage_title, useSecondWeaponSet='false')
        slot_entries = {}
        for item in data.get('inventory_slots', []):
            key = f'{item["inventory_id"]}:{item.get("slot_x", 0)}'
            slot = catalog['slots'].get(key) if item.get('slot_y', 0) == 0 else None
            if not slot:
                stage['unmapped_slots'].append(key)
                unresolved = True
                continue
            hint = '\n'.join(str(item[k]) for k in ('unique_name', 'additional_text') if item.get(k))
            if slot in slot_entries:
                previous = slot_entries[slot]
                if item.get('raw_text'):
                    raise ConversionError(f'{stage_title}: mais de um item no slot {slot}', report)
                previous.set('note', previous.get('note', '') + '\n' + hint)
                stage['warnings'].append(f'Sugestões alternativas de {slot} mantidas nas notas')
                continue
            slot_el = ET.SubElement(itemset, 'Slot', name=slot, itemId='0', note=hint)
            slot_entries[slot] = slot_el
            raw_text = item.get('raw_text')
            if raw_text:
                if not isinstance(raw_text, str) or not re.match(r'^Rarity: (NORMAL|MAGIC|RARE|UNIQUE)\r?\n', raw_text, re.I):
                    raise ConversionError(f'{stage_title}: raw_text precisa ser texto de item PoB com Rarity', report)
                item_counter += 1
                ET.SubElement(items, 'Item', id=str(item_counter)).text = raw_text
                slot_el.set('itemId', str(item_counter))
            else:
                stage['warnings'].append(f'{slot}: apenas sugestão; atributos não disponíveis')
        stage['mapped_passives'] = len(node_ids)
        notes.extend(['', f'=== {stage_title} ===', json.dumps(data, ensure_ascii=False, indent=2)])
    if report['skipped']:
        notes.extend(['', '=== Ignored files ===', json.dumps(report['skipped'], ensure_ascii=False, indent=2)])
    if unresolved:
        report['warnings'].append('Dados sem correspondência; consulte unmapped_* em cada estágio')
        if not allow_partial:
            raise ConversionError('Há IDs sem mapeamento. Corrija o mapa ou use --allow-partial explicitamente', report)
        notes.append('PARTIAL CONVERSION: unmapped IDs were omitted from active sets. See original JSON and report.')
    ET.SubElement(root, 'Notes').text = '\n'.join(notes)
    ET.SubElement(root, 'Config')
    ET.indent(root)
    xml = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    code = encode(xml)
    validate_roundtrip(xml, code, len(stages))
    report.update(roundtrip_ok=True, xml_sha256=hashlib.sha256(xml).hexdigest(), partial=unresolved)
    return xml, code, report


def write_outputs(prefix, xml, code, report):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = [Path(str(prefix) + suffix) for suffix in ('.xml', '.txt', '.report.json')]
    for path in paths:
        if path.exists():
            raise ConversionError(f'Saída já existe: {path}. Escolha outro nome')
    paths[0].write_bytes(xml)
    paths[1].write_text(code + '\n', encoding='ascii')
    paths[2].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return paths


def main(argv=None):
    p = argparse.ArgumentParser(description='Vários .build -> um PoB2, sem dependências externas')
    p.add_argument('files', nargs='*', help='Arquivos, pastas ou padrões *.build')
    p.add_argument('-o', '--output', default='merged', help='Prefixo dos arquivos de saída')
    p.add_argument('--catalog', default=str(DEFAULT_CATALOG))
    p.add_argument('--map', dest='map_path', help='Mapa JSON de passivas alternativo')
    p.add_argument('--tree-version', help='Deve coincidir com o catálogo, ex.: 0_5')
    p.add_argument('--class', dest='class_name', help='Classe para estágios sem ascendência, ex.: Monk')
    p.add_argument('--keep-order', action='store_true', help='Preservar ordem dos argumentos')
    p.add_argument('--allow-partial', action='store_true', help='Omitir IDs desconhecidos, mantendo relatório e notas')
    p.add_argument('--title', default='Merged build')
    p.add_argument('--gui', action='store_true')
    p.add_argument('--validate', metavar='CODE_TXT', help='Validar código e estrutura XML, sem converter')
    args = p.parse_args(argv)
    if args.gui:
        from gui import launch
        launch()
        return 0
    try:
        if args.validate:
            code = Path(args.validate).read_text(encoding='ascii')
            validate_roundtrip(decode(code), code)
            print('Código, XML e referências de conjuntos válidos.')
            return 0
        paths = []
        for value in args.files:
            path = Path(value)
            paths.extend(sorted(path.glob('*.build')) if path.is_dir() else (glob.glob(value) or [value]))
        if not paths:
            p.error('Selecione arquivos .build ou use --gui')
        result = convert(paths, args.catalog, args.map_path, args.tree_version, args.class_name,
                         args.keep_order, args.allow_partial, args.title)
        for path in write_outputs(args.output, *result):
            print(path)
        print(f'{len(result[2]["stages"])} estágios; {len(result[2]["skipped"])} ignorados; round-trip OK.')
        return 0
    except (OSError, ValueError, KeyError, zlib.error) as e:
        print(f'Erro: {e}', file=sys.stderr)
        if isinstance(e, ConversionError) and e.report:
            # No output files on conversion failure; diagnostics remain available to CLI callers.
            print(json.dumps(e.report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
