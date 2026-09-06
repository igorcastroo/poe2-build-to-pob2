"""Extract JSON mappings from a local PoB2 source tree; never execute Lua."""
import argparse
import json
import re
from pathlib import Path


def extract(source, version):
    source = Path(source)
    if (source / 'src').is_dir():
        source /= 'src'
    tree = json.loads((source / 'TreeData' / version / 'tree.json').read_text(encoding='utf-8'))
    nodes = {}
    for node in tree['nodes'].values():
        if node.get('stringId') and 'skill' in node:
            key, value = node['stringId'], node['skill']
            if key in nodes and nodes[key] != value:
                raise ValueError(f'Ambiguous passive: {key}')
            nodes[key] = value
    gems = {}
    lua = (source / 'Data/Gems.lua').read_text(encoding='utf-8')
    for block in re.split(r'\n\t\["', lua)[1:]:
        def field(name):
            m = re.search(r'\n\t\t' + name + r' = "([^"\n]*)"', block)
            return m.group(1) if m else None
        game_id = field('gameId')
        if game_id:
            entry = {k: v for k, v in {'nameSpec': field('name'), 'variantId': field('variantId')}.items() if v}
            if game_id in gems and gems[game_id] != entry:
                raise ValueError(f'Ambiguous gem: {game_id}')
            gems[game_id] = entry
    slots = {}
    lua = (source / 'Data/InventorySlots.lua').read_text(encoding='utf-8')
    for name, game_id, x in re.findall(r'\["([^"]+)"\] = \{ id = "([^"]+)", slot_x = (\d+)', lua):
        slots[f'{game_id}:{x}'] = name
    # Official Build Planner exports use Charm1:0..2, while some PoB2 data
    # snapshots expose those same slots as Flask1:2..4.
    for index in range(3):
        flask_slot = slots.get(f'Flask1:{index + 2}')
        if flask_slot:
            slots.setdefault(f'Charm1:{index}', flask_slot)
    quest_rewards = []
    quest_lua = (source / 'Data/QuestRewards.lua').read_text(encoding='utf-8')
    for block in re.findall(r'\n\t\{\n(.*?)\n\t\},', quest_lua, re.S):
        def quest_field(name):
            match = re.search(r'\["' + re.escape(name) + r'"\] = "([^"\n]*)"', block)
            return match.group(1) if match else None
        row = {name: quest_field(name) for name in ('Description', 'Area', 'Info', 'Stat')}
        row = {name: value for name, value in row.items() if value is not None}
        options = re.search(r'\["Options"\] = \{(.*?)\n\t\t\},', block, re.S)
        if options:
            row['Options'] = [value.replace(r'\n', '\n').replace(r'\t', '\t')
                              for value in re.findall(r'"([^"\n]*)"', options.group(1))]
        if 'Description' not in row or 'Area' not in row or 'Info' not in row:
            raise ValueError('Quest reward extraction found an incomplete entry')
        row['useConfig'] = '["useConfig"] = false' not in block
        quest_rewards.append(row)
    classes = [{ 'name': c['name'], 'integerId': c['integerId'],
                 'ascendancies': [{ 'name': a['name'], 'internalId': a['internalId']} for a in c['ascendancies']]}
               for c in tree['classes']]
    if not nodes or not gems or not slots or not classes:
        raise ValueError('Catalog extraction produced an empty section')
    return {'tree_version': version, 'source': 'PathOfBuildingCommunity/PathOfBuilding-PoE2',
            'passives': nodes, 'gems': gems, 'slots': slots, 'classes': classes,
            'quest_rewards': quest_rewards}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Extrai mapa JSON dos dados locais do PoB2')
    p.add_argument('pob_directory')
    p.add_argument('--tree-version', required=True)
    p.add_argument('-o', '--output', required=True)
    args = p.parse_args()
    Path(args.output).write_text(json.dumps(extract(args.pob_directory, args.tree_version), ensure_ascii=False, indent=2), encoding='utf-8')
