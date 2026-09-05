# PoB2 Stage Merger

**Build → PoB2** merges multiple Mobalytics / PoE2 `.build` stages into one Path of Building 2 build.

Converte vários arquivos `.build` JSON do Mobalytics / planejador do PoE2 em **um XML do PoB2**, um **código de importação** e um **relatório JSON**. Python 3.10 ou mais recente, sem pacotes externos. A interface usa Tkinter, incluído na instalação padrão do Python para Windows.

## Executável Windows

Abra `Build2PoB2.exe`. Ele é a versão pronta para Windows, inclui Python, Tkinter e o catálogo da árvore 0_5; não requer instalação de Python nem conexão com a internet. A tela abre em Português (Brasil). Use as bandeiras no topo para alternar, a qualquer momento, entre **🇧🇷 Português (Brasil)** e **🇺🇸 English (US)**.

## Abrir a interface pelo código-fonte

1. Extraia o ZIP inteiro para uma pasta.
2. Abra **Abrir Conversor.bat**.
3. Adicione os arquivos `.build`. A lista é ordenada automaticamente; use Subir/Descer para ajustar.
4. Informe a classe apenas quando ela não puder ser identificada pela ascendência dos arquivos.
5. Clique em **Gerar PoB2**, escolha um nome novo e depois em **Copiar código**.
6. No PoB2: **Import/Export Build → Import from Code**.

São gerados `nome.xml`, `nome.txt` e `nome.report.json`. O programa não substitui saídas existentes. O XML também pode ser colocado na pasta de builds do PoB2.

Se o Windows não reconhecer `python`, instale Python com Tkinter e a opção de adicionar ao PATH, ou execute `py converter.py --gui` no terminal aberto nesta pasta.

## CLI

Execute estes comandos dentro da pasta extraída:

```powershell
python converter.py "C:\MeusGuias\*.build" --class Monk -o "C:\MeusGuias\GigaBonk"
python converter.py "Act 1.build" "Act 2.build" "Mirror Tier.build" --keep-order --class Monk -o resultado
python converter.py "C:\MeusGuias" --map passives.json --class Monk -o resultado
python converter.py --validate resultado.txt
python converter.py --gui
```

Sem `--keep-order`, a ordenação usa o **nome do arquivo**: Act/Ato 1… → Interludes → Early → Mid → Late → High → Mirror. Nomes não reconhecidos vêm depois, em ordem natural. Variantes dentro de uma mesma fase são ordenadas pelo nome. Na GUI a ordem final da lista sempre prevalece.

Código de saída: `0` em caso de sucesso, `2` em caso de erro. Arquivos corrompidos, vazios, de versão diferente ou com estrutura inválida são ignorados e identificados no relatório. Se nenhum arquivo válido restar, nenhum PoB é produzido. Erros impeditivos mostram o diagnóstico no terminal; a API Python também disponibiliza `ConversionError.report`.

## Mapa de passivas e versões

O catálogo incluído contém **4.914 IDs de passivas**, **967 gems**, classes/ascendências e slots extraídos do repositório público do PoB2, árvore **0_5**. A versão de jogo **0.5.5** usa esse identificador de árvore, mas a existência de um ID no mapa não prova que os balanceamentos sejam idênticos entre patches.

O mapa segue a associação presente no PoB2: `stringId` interno da GGG → `skill` numérico, equivalente ao hash da passiva usado pelo PoB. IDs desconhecidos **não são convertidos por semelhança de nome**. Por padrão interrompem a conversão; `--allow-partial` permite omiti-los dos conjuntos ativos e mantê-los nas notas e no relatório. A interface oferece a mesma opção, desmarcada inicialmente.

`--map` aceita os formatos abaixo. O mapa substitui completamente a seção de passivas; não há complementação silenciosa pelo catálogo padrão.

```json
{"id_interno": 12345}
```

```json
[{"Id": "id_interno", "PassiveSkillsHash": 12345}]
```

```json
{"id_interno": {"PassiveSkillsHash": 12345}}
```

```json
{"tree_version": "0_5", "passives": {"id_interno": 12345}}
```

Os IDs acima ilustram a estrutura; **não são um mapa para jogar**. Use os IDs reais do catálogo ou do seu `passives.json`. Hashes negativos, fora de 16 bits, fracionários, booleanos e IDs com associações conflitantes são rejeitados. Mapas sem versão são interpretados como pertencentes à versão do catálogo selecionado, sob responsabilidade de quem forneceu o mapa.

Para atualizar todos os dados a partir de uma pasta do PoB2 que contenha `TreeData/<versão>/tree.json`, `Data/Gems.lua` e `Data/InventorySlots.lua`:

```powershell
python catalog_tools.py "C:\PoB2" --tree-version 0_5 -o catalog-atual.json
python converter.py "C:\MeusGuias\*.build" --catalog catalog-atual.json --class Monk -o resultado
```

Uma cópia do repositório oficial também serve como origem. O extrator **lê os dados sem executar Lua**. Se o formato upstream mudar ou houver ambiguidades, ele interrompe. Um catálogo para outra versão deve substituir o catálogo inteiro, não apenas mudar o número em `--tree-version`.

## O que é preservado

- Um Tree Spec, Skill Set e Item Set com o mesmo título para cada estágio válido.
- Passivas mapeadas, conjuntos de armas 1/2 e notas por nó.
- Gems e suportes vinculados por IDs exatos do catálogo; notas nas gems.
- Descrição, autor, link, notas, intervalos e campos adicionais no JSON original incorporado às Notes e ao relatório.
- Sugestões de equipamento em notas dos slots, inclusive nomes de únicos.

Um `.build` oficial frequentemente contém **orientações de equipamento**, não itens completos. Um nome de único não informa seus rolls. O programa cria o Item Set e suas notas, deixando `itemId=0` quando não há texto completo; não inventa base, afixos ou valores. Para fontes que disponibilizam texto real de item PoB, é aceita a extensão `raw_text` em uma entrada de `inventory_slots`, começando por `Rarity: ...`. O texto é copiado literalmente e o item recebe uma referência exclusiva. A interpretação de bases/mods desse texto continua a cargo do PoB2.

`level_interval` indica quando algo é recomendado para o personagem; **não é nível da gem**. Quando a entrada fornece explicitamente `level` e `quality`, eles são preservados. Caso contrário o XML deixa esses valores ausentes, e o PoB aplica seus próprios padrões. Não são inferidos números a partir de prosa ou prioridades de equipamento.

Não são reconstruídos cálculos de DPS, configurações de combate, modificadores de itens descritos em prosa, escolhas de atributos/masteries a partir de notas, ligações de árvores ou intervalos como estágios extras. Notas de intervalos ficam preservadas; cada arquivo continua representando um estágio. Para arquivos que não seguem o esquema JSON oficial, será necessário um adaptador específico.

## Validação e referência Giga Bonk

O fluxo implementado segue o resultado descrito no histórico: múltiplos `.build` → um PoB2 → conjuntos por estágio → IDs internos mapeados → XML → zlib → Base64 URL-safe.

A validação automática verifica a igualdade exata **XML → compressão/código → descompressão/XML**, a estrutura dos conjuntos e as referências dos itens. Os testes cobrem ordenação, arquivos inválidos, IDs desconhecidos, notas Unicode, armas, gems, slots, versões e proteção contra sobrescrita.

```powershell
python -m unittest discover -s tests -v
```

**Limite da validação:** os `.build` e o PoB final originais do Giga Bonk não estavam disponíveis nos anexos recuperados. Portanto, esta entrega não afirma reproduzir aqueles 9 estágios/208 nós nem ter sido importada interativamente no PoB2. O XML foi conferido contra os carregadores públicos do PoB2, e o round-trip não substitui uma conferência visual da árvore no aplicativo. Os exemplos incluídos são dados de teste, não o guia Giga Bonk.

## Fontes

- [Esquema oficial GGG para .build](https://www.pathofexile.com/developer/docs/game#buildplanner)
- [PoB2 — código e dados](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2)
- Snapshot usado: `3887ae68a6a6b8bb7b41d1b61998f1aa184201e4`.
- Campos XML conferidos em `PassiveSpec.lua`, `SkillsTab.lua`, `ItemsTab.lua`, `TreeTab.lua`, `Build.lua` e `GameVersions.lua` desse snapshot.

O catálogo contém dados de jogo © Grinding Gear Games derivados do PoB2. Consulte `THIRD_PARTY_LICENSES.md` para os avisos do projeto de origem.
