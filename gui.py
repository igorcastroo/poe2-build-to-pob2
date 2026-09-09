"""Small native Tk interface; all conversion runs locally."""
from pathlib import Path
import json
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from converter import DEFAULT_CATALOG, ConversionError, convert, write_outputs, stage_key
from mobalytics import MobalyticsImportError, decode_pob2_code, import_guide

TEXT = {
    'pt-BR': {
        'title': 'PoE2 Build to PoB2 | Mobalytics → PoB2', 'headline': 'Guias Mobalytics. Um único PoB2.',
        'subtitle': 'Importe uma URL ou .builds e gere árvore, skills, itens e código PoB2 por estágio.',
        'add': 'Adicionar arquivos', 'remove': 'Remover', 'up': '↑ Subir', 'down': '↓ Descer', 'sort': 'Ordenar estágios',
        'url': 'Link do guia Mobalytics', 'import_url': 'Importar guia',
        'url_needed': 'Cole um link público do guia Mobalytics.', 'import_error': 'Não foi possível importar o guia',
        'imported': '{stages} estágios importados de:\n{guide}\nArquivos temporários válidos foram adicionados à lista.\n{rewards} escolha(s) de recompensa foram registradas; as compatíveis serão ativadas em Config → Quest Rewards ao gerar.',
        'import_rejected': '\n\n{count} variante(s) rejeitada(s):\n{details}',
        'direct_pob': '{guide} já possui um código PoB2 válido. Ele foi usado diretamente; nenhum .build foi baixado ou convertido.',
        'direct_saved': 'Código PoB2 original salvo sem conversão.\n{paths}',
        'mapping': 'Mapa alternativo (opcional)', 'class': 'Classe (se não identificada)', 'choose': 'Selecionar',
        'partial': 'Permitir conversão parcial: omitir IDs desconhecidos e registrar no relatório', 'generate': 'Gerar PoB2…', 'copy': 'Copiar código',
        'welcome': 'Importe guias Mobalytics ou arquivos .build. Cada estágio gera árvore, skills e itens editáveis quando a base é confirmada.\nO catálogo incluído corresponde à árvore 0_5.',
        'files_title': 'Selecionar arquivos', 'files_needed': 'Adicione pelo menos um arquivo .build.', 'save_title': 'Salvar PoB2', 'save_name': 'merged.xml',
        'built': '{stages} estágios gerados. Round-trip validado.\n{skipped} arquivos ignorados; {warnings} observações; parcial: {partial}.\n{paths}\nNo PoB2: Import/Export Build → Import from Code.',
        'error_title': 'Não foi possível converter', 'copied': 'Código copiado. Cole no PoB2 → Import/Export Build → Import from Code.',
        'all_files': 'Todos', 'build_files': 'PoE2 builds', 'json_files': 'JSON', 'auto_copied': 'Código de importação copiado automaticamente.', 'import_code_label': 'Código para colar no PoB2 → Import/Export Build → Import from Code:',
    },
    'en-US': {
        'title': 'PoE2 Build to PoB2 | Mobalytics → PoB2', 'headline': 'Mobalytics guides. One PoB2.',
        'subtitle': 'Import a URL or .build files to create staged trees, skills, items, and a PoB2 code.',
        'url': 'Mobalytics guide URL', 'import_url': 'Import guide',
        'url_needed': 'Paste a public Mobalytics guide URL.', 'import_error': 'Could not import guide',
        'imported': '{stages} stages imported from:\n{guide}\nValidated temporary files were added to the list.\n{rewards} quest reward choice(s) were recorded; compatible choices will be enabled in Config → Quest Rewards when you create the PoB2.',
        'import_rejected': '\n\n{count} rejected variant(s):\n{details}',
        'direct_pob': '{guide} already has a valid PoB2 code. It was used directly; no .build files were downloaded or converted.',
        'direct_saved': 'Original PoB2 code saved without conversion.\n{paths}',
        'add': 'Add files', 'remove': 'Remove', 'up': '↑ Move up', 'down': '↓ Move down', 'sort': 'Sort stages',
        'mapping': 'Alternate map (optional)', 'class': 'Class (when not detected)', 'choose': 'Browse',
        'partial': 'Allow partial conversion: omit unknown IDs and record them in the report', 'generate': 'Create PoB2…', 'copy': 'Copy code',
        'welcome': 'Import Mobalytics guides or .build files. Each stage creates a tree, skills, and editable items when its base is confirmed.\nThe bundled catalog matches tree 0_5.',
        'files_title': 'Select files', 'files_needed': 'Add at least one .build file.', 'save_title': 'Save PoB2', 'save_name': 'merged.xml',
        'built': '{stages} stages created. Round-trip validated.\n{skipped} files skipped; {warnings} notes; partial: {partial}.\n{paths}\nIn PoB2: Import/Export Build → Import from Code.',
        'error_title': 'Could not convert', 'copied': 'Code copied. Paste it in PoB2 → Import/Export Build → Import from Code.',
        'all_files': 'All files', 'build_files': 'PoE2 builds', 'json_files': 'JSON', 'auto_copied': 'Import code copied automatically.', 'import_code_label': 'Code to paste in PoB2 → Import/Export Build → Import from Code:',
    },
}

TEXT['pt-BR']['advanced'] = 'Avançado'
TEXT['en-US']['advanced'] = 'Advanced'


class App:
    def __init__(self, root):
        self.root = root
        root.geometry('850x670'); root.minsize(700, 560)
        self.files, self.code, self.direct_build, self.active_file = [], None, None, None
        self.mobalytics_import = False
        self.import_temp = tempfile.TemporaryDirectory(prefix='poe2-build-to-pob2-')
        self.locale = tk.StringVar(value='pt-BR')
        self.catalog = tk.StringVar(value=str(DEFAULT_CATALOG))
        self.mapping, self.cls = tk.StringVar(), tk.StringVar()
        # Normal imports finish even when a guide contains a newer ID; every
        # omitted value remains listed in the generated report.
        self.partial = tk.BooleanVar(value=True)
        self.guide_url = tk.StringVar()
        self.classes = [c['name'] for c in json.loads(DEFAULT_CATALOG.read_text(encoding='utf-8'))['classes']]
        self.build()

    @property
    def t(self): return TEXT[self.locale.get()]

    def build(self):
        for child in self.root.winfo_children(): child.destroy()
        self.root.title(self.t['title'])
        frame = ttk.Frame(self.root, padding=16); frame.pack(fill='both', expand=True)
        language_bar = ttk.Frame(frame); language_bar.pack(fill='x')
        ttk.Label(language_bar, text='Language / Idioma:').pack(side='left')
        self.br = ttk.Button(language_bar, text='🇧🇷  Português (Brasil)', command=lambda: self.set_locale('pt-BR'))
        self.us = ttk.Button(language_bar, text='🇺🇸  English (US)', command=lambda: self.set_locale('en-US'))
        self.br.pack(side='left', padx=(8, 4)); self.us.pack(side='left')
        (self.br if self.locale.get() == 'pt-BR' else self.us).state(['disabled'])
        ttk.Label(frame, text=self.t['headline'], font=('Segoe UI', 16, 'bold')).pack(anchor='w', pady=(14, 0))
        ttk.Label(frame, text=self.t['subtitle']).pack(anchor='w', pady=(4, 12))
        buttons = ttk.Frame(frame); buttons.pack(fill='x')
        for label, callback in [(self.t['add'], self.add), (self.t['remove'], self.remove), (self.t['up'], lambda: self.move(-1)), (self.t['down'], lambda: self.move(1)), (self.t['sort'], self.sort)]:
            ttk.Button(buttons, text=label, command=callback).pack(side='left', padx=(0, 6))
        guide = ttk.Frame(frame); guide.pack(fill='x', pady=(10, 0)); guide.columnconfigure(1, weight=1)
        ttk.Label(guide, text=self.t['url']).grid(row=0, column=0, sticky='w', padx=(0, 12))
        ttk.Entry(guide, textvariable=self.guide_url).grid(row=0, column=1, sticky='ew')
        ttk.Button(guide, text=self.t['import_url'], command=self.import_url).grid(row=0, column=2, padx=(8, 0))
        self.listbox = tk.Listbox(frame, height=10, exportselection=False); self.listbox.pack(fill='both', expand=True, pady=10)
        advanced_tabs = ttk.Notebook(frame); advanced_tabs.pack(fill='x', pady=(0, 8))
        options = ttk.Frame(advanced_tabs, padding=8); options.columnconfigure(1, weight=1)
        advanced_tabs.add(options, text=self.t['advanced'])
        for row, label, variable in [(0, self.t['mapping'], self.mapping)]:
            ttk.Label(options, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
            ttk.Entry(options, textvariable=variable).grid(row=row, column=1, sticky='ew')
            ttk.Button(options, text=self.t['choose'], command=lambda v=variable: self.select_json(v)).grid(row=row, column=2, padx=(8, 0))
        ttk.Label(options, text=self.t['class']).grid(row=1, column=0, sticky='w', pady=4)
        ttk.Combobox(options, textvariable=self.cls, values=[''] + self.classes).grid(row=1, column=1, sticky='ew')
        ttk.Checkbutton(options, text=self.t['partial'], variable=self.partial).grid(row=2, column=0, columnspan=3, sticky='w', pady=(8, 0))
        bar = ttk.Frame(frame); bar.pack(fill='x')
        ttk.Button(bar, text=self.t['generate'], command=self.generate).pack(side='left')
        self.copy_button = ttk.Button(bar, text=self.t['copy'], command=self.copy, state='normal' if self.code else 'disabled'); self.copy_button.pack(side='left', padx=8)
        self.status = tk.Text(frame, height=7, wrap='word', state='disabled'); self.status.pack(fill='x', pady=(12, 0))
        self.refresh(); self.log(self.t['welcome'])

    def set_locale(self, locale):
        self.locale.set(locale); self.build()

    def log(self, text):
        self.status.configure(state='normal'); self.status.delete('1.0', 'end'); self.status.insert('1.0', text); self.status.configure(state='disabled')

    def refresh(self, selected=None):
        self.listbox.delete(0, 'end')
        for i, path in enumerate(self.files, 1): self.listbox.insert('end', f'{i:02d}  {Path(path).name}')
        if selected is not None: self.listbox.selection_set(selected)

    def add(self):
        paths = filedialog.askopenfilenames(filetypes=[(self.t['build_files'], '*.build'), (self.t['all_files'], '*.*')])
        if paths:
            self.direct_build = None
            self.active_file = None
            self.mobalytics_import = False
            self.files.extend(path for path in paths if path not in self.files); self.sort()

    def import_url(self):
        url = self.guide_url.get().strip()
        if not url:
            messagebox.showinfo(self.t['import_error'], self.t['url_needed']); return
        self.root.configure(cursor='watch'); self.root.update_idletasks()
        try:
            result = import_guide(url, self.import_temp.name)
            if result.pob_code:
                xml = decode_pob2_code(result.pob_code)
                self.files.clear(); self.refresh()
                self.mobalytics_import = False
                self.direct_build = (xml, result.pob_code, {
                    'source': {'provider': 'Mobalytics', 'guide_url': url, 'mode': 'direct_pob2_code'},
                    'roundtrip_ok': True, 'stages': [],
                })
                self.show_import_code(result.pob_code, self.t['direct_pob'].format(guide=result.guide_name))
                return
            self.direct_build = None
            self.mobalytics_import = True
            self.files.extend(str(path) for path in result.files if str(path) not in self.files)
            self.active_file = str(result.active_file) if result.active_file else None
            self.sort()
            generated = convert(self.files, catalog_path=self.catalog.get(), map_path=self.mapping.get() or None,
                                class_name=self.cls.get() or None, manual_order=True,
                                allow_partial=self.partial.get(), active_path=self.active_file,
                                flatten_weapon_sets=self.mobalytics_import)
            message = self.t['imported'].format(stages=len(result.files), guide=result.guide_name,
                                                rewards=result.quest_rewards)
            if result.rejected:
                message += self.t['import_rejected'].format(count=len(result.rejected), details='\n'.join(result.rejected))
            self.show_import_code(generated[1], message)
        except (MobalyticsImportError, OSError, ValueError) as e:
            self.log(str(e)); messagebox.showerror(self.t['import_error'], str(e))
        finally:
            self.root.configure(cursor='')

    def remove(self):
        self.direct_build = None
        for i in reversed(self.listbox.curselection()):
            removed = self.files.pop(i)
            if removed == self.active_file:
                self.active_file = None
        self.refresh()

    def move(self, direction):
        selected = self.listbox.curselection()
        if selected and 0 <= selected[0] + direction < len(self.files):
            i, j = selected[0], selected[0] + direction; self.files[i], self.files[j] = self.files[j], self.files[i]; self.refresh(j)

    def sort(self): self.files.sort(key=lambda p: stage_key(Path(p).stem)); self.refresh()

    def select_json(self, variable):
        path = filedialog.askopenfilename(filetypes=[(self.t['json_files'], '*.json')])
        if path: variable.set(path)

    def generate(self):
        if not self.files and not self.direct_build:
            messagebox.showinfo(self.t['files_title'], self.t['files_needed']); return
        self.code = None; self.copy_button.configure(state='disabled')
        guide_url_before = self.guide_url.get()
        try:
            result = self.direct_build or convert(self.files, catalog_path=self.catalog.get(), map_path=self.mapping.get() or None, class_name=self.cls.get() or None, manual_order=True, allow_partial=self.partial.get(), active_path=self.active_file, flatten_weapon_sets=self.mobalytics_import)
            destination = filedialog.asksaveasfilename(title=self.t['save_title'], defaultextension='.xml', initialfile=self.t['save_name'], filetypes=[('PoB2 XML', '*.xml')])
            if not destination: return
            paths = write_outputs(str(Path(destination).with_suffix('')), *result, overwrite=True)
            if self.direct_build:
                self.guide_url.set(guide_url_before)
                self.show_import_code(result[1], self.t['direct_saved'].format(paths='\n'.join(str(p) for p in paths)))
                return
            report = result[2]
            self.guide_url.set(guide_url_before)
            message = self.t['built'].format(stages=len(report['stages']), skipped=len(report['skipped']), warnings=sum(len(s['warnings']) for s in report['stages']), partial=report['partial'], paths='\n'.join(str(p) for p in paths))
            self.show_import_code(result[1], message)
        except (OSError, ValueError, KeyError) as e:
            details = str(e)
            if isinstance(e, ConversionError) and e.report: details += '\n' + json.dumps(e.report, ensure_ascii=False, indent=2)
            self.log(details); messagebox.showerror(self.t['error_title'], str(e))

    def show_import_code(self, code, message):
        self.code = code
        self.copy_button.configure(state='normal')
        self.root.clipboard_clear()
        self.root.clipboard_append(self.code)
        self.log(message + '\n' + self.t['auto_copied'] + '\n\n' + self.t['import_code_label'] + '\n' + self.code)
        self.status.see('end')

    def copy(self):
        if self.code:
            self.root.clipboard_clear(); self.root.clipboard_append(self.code); self.log(self.t['copied'])


def launch():
    root = tk.Tk(); App(root); root.mainloop()


if __name__ == '__main__': launch()
