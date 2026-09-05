"""Small native Tk interface; all conversion runs locally."""
from pathlib import Path
import json
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from converter import DEFAULT_CATALOG, ConversionError, convert, write_outputs, stage_key
from mobalytics import MobalyticsImportError, import_guide

TEXT = {
    'pt-BR': {
        'title': 'Build → PoB2 | Conversor de estágios', 'headline': 'Vários estágios. Um único PoB2.',
        'subtitle': 'Adicione os .build, confira a ordem e gere XML + código de importação.',
        'add': 'Adicionar arquivos', 'remove': 'Remover', 'up': '↑ Subir', 'down': '↓ Descer', 'sort': 'Ordenar estágios',
        'url': 'Link do guia Mobalytics', 'import_url': 'Importar guia',
        'url_needed': 'Cole um link p?blico do guia Mobalytics.', 'import_error': 'N?o foi poss?vel importar o guia',
        'imported': '{stages} est?gios importados de:\n{guide}\nArquivos tempor?rios v?lidos foram adicionados ? lista.',
        'import_rejected': '\n\n{count} variante(s) rejeitada(s):\n{details}',
        'url': 'Mobalytics guide URL', 'import_url': 'Import guide',
        'url_needed': 'Paste a public Mobalytics guide URL.', 'import_error': 'Could not import guide',
        'imported': '{stages} stages imported from:\n{guide}\nValidated temporary files were added to the list.',
        'import_rejected': '\n\n{count} rejected variant(s):\n{details}',
        'mapping': 'Mapa alternativo (opcional)', 'class': 'Classe (se não identificada)', 'choose': 'Selecionar',
        'partial': 'Permitir conversão parcial: omitir IDs desconhecidos e registrar no relatório', 'generate': 'Gerar PoB2…', 'copy': 'Copiar código',
        'welcome': 'Tudo funciona localmente. Equipamentos descritos apenas como sugestões ficam nas notas.\nO catálogo incluído corresponde à árvore 0_5.',
        'files_title': 'Selecionar arquivos', 'files_needed': 'Adicione pelo menos um arquivo .build.', 'save_title': 'Salvar PoB2', 'save_name': 'merged.xml',
        'built': '{stages} estágios gerados. Round-trip validado.\n{skipped} arquivos ignorados; {warnings} observações; parcial: {partial}.\n{paths}\nNo PoB2: Import/Export Build → Import from Code.',
        'error_title': 'Não foi possível converter', 'copied': 'Código copiado. Cole no PoB2 → Import/Export Build → Import from Code.',
        'all_files': 'Todos', 'build_files': 'PoE2 builds', 'json_files': 'JSON',
    },
    'en-US': {
        'title': 'Build → PoB2 | Stage Converter', 'headline': 'Many stages. One PoB2.',
        'subtitle': 'Add .build files, review their order, then create XML and an import code.',
        'add': 'Add files', 'remove': 'Remove', 'up': '↑ Move up', 'down': '↓ Move down', 'sort': 'Sort stages',
        'mapping': 'Alternate map (optional)', 'class': 'Class (when not detected)', 'choose': 'Browse',
        'partial': 'Allow partial conversion: omit unknown IDs and record them in the report', 'generate': 'Create PoB2…', 'copy': 'Copy code',
        'welcome': 'Everything runs locally. Equipment described only as guidance remains in notes.\nThe bundled catalog matches tree 0_5.',
        'files_title': 'Select files', 'files_needed': 'Add at least one .build file.', 'save_title': 'Save PoB2', 'save_name': 'merged.xml',
        'built': '{stages} stages created. Round-trip validated.\n{skipped} files skipped; {warnings} notes; partial: {partial}.\n{paths}\nIn PoB2: Import/Export Build → Import from Code.',
        'error_title': 'Could not convert', 'copied': 'Code copied. Paste it in PoB2 → Import/Export Build → Import from Code.',
        'all_files': 'All files', 'build_files': 'PoE2 builds', 'json_files': 'JSON',
    },
}


class App:
    def __init__(self, root):
        self.root = root
        root.geometry('850x670'); root.minsize(700, 560)
        self.files, self.code = [], None
        self.import_temp = tempfile.TemporaryDirectory(prefix='poe2-build-to-pob2-')
        self.locale = tk.StringVar(value='pt-BR')
        self.catalog = tk.StringVar(value=str(DEFAULT_CATALOG))
        self.mapping, self.cls, self.partial = tk.StringVar(), tk.StringVar(), tk.BooleanVar()
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
        options = ttk.Frame(frame); options.pack(fill='x'); options.columnconfigure(1, weight=1)
        for row, label, variable in [(0, self.t['mapping'], self.mapping)]:
            ttk.Label(options, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
            ttk.Entry(options, textvariable=variable).grid(row=row, column=1, sticky='ew')
            ttk.Button(options, text=self.t['choose'], command=lambda v=variable: self.select_json(v)).grid(row=row, column=2, padx=(8, 0))
        ttk.Label(options, text=self.t['class']).grid(row=1, column=0, sticky='w', pady=4)
        ttk.Combobox(options, textvariable=self.cls, values=[''] + self.classes).grid(row=1, column=1, sticky='ew')
        ttk.Checkbutton(frame, text=self.t['partial'], variable=self.partial).pack(anchor='w', pady=8)
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
        self.files.extend(path for path in paths if path not in self.files); self.sort()

    def import_url(self):
        url = self.guide_url.get().strip()
        if not url:
            messagebox.showinfo(self.t['import_error'], self.t['url_needed']); return
        self.root.configure(cursor='watch'); self.root.update_idletasks()
        try:
            result = import_guide(url, self.import_temp.name)
            self.files.extend(str(path) for path in result.files if str(path) not in self.files)
            self.sort()
            message = self.t['imported'].format(stages=len(result.files), guide=result.guide_name)
            if result.rejected:
                message += self.t['import_rejected'].format(count=len(result.rejected), details='\n'.join(result.rejected))
            self.log(message)
        except (MobalyticsImportError, OSError, ValueError) as e:
            self.log(str(e)); messagebox.showerror(self.t['import_error'], str(e))
        finally:
            self.root.configure(cursor='')

    def remove(self):
        for i in reversed(self.listbox.curselection()): self.files.pop(i)
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
        if not self.files:
            messagebox.showinfo(self.t['files_title'], self.t['files_needed']); return
        self.code = None; self.copy_button.configure(state='disabled')
        try:
            result = convert(self.files, catalog_path=self.catalog.get(), map_path=self.mapping.get() or None, class_name=self.cls.get() or None, manual_order=True, allow_partial=self.partial.get())
            destination = filedialog.asksaveasfilename(title=self.t['save_title'], defaultextension='.xml', initialfile=self.t['save_name'], filetypes=[('PoB2 XML', '*.xml')])
            if not destination: return
            paths = write_outputs(str(Path(destination).with_suffix('')), *result)
            self.code = result[1]; self.copy_button.configure(state='normal'); report = result[2]
            self.log(self.t['built'].format(stages=len(report['stages']), skipped=len(report['skipped']), warnings=sum(len(s['warnings']) for s in report['stages']), partial=report['partial'], paths='\n'.join(str(p) for p in paths)))
        except (OSError, ValueError, KeyError) as e:
            details = str(e)
            if isinstance(e, ConversionError) and e.report: details += '\n' + json.dumps(e.report, ensure_ascii=False, indent=2)
            self.log(details); messagebox.showerror(self.t['error_title'], str(e))

    def copy(self):
        if self.code:
            self.root.clipboard_clear(); self.root.clipboard_append(self.code); self.log(self.t['copied'])


def launch():
    root = tk.Tk(); App(root); root.mainloop()


if __name__ == '__main__': launch()
