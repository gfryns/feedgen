from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, ProgressBar, Select
from textual.containers import Vertical, Horizontal, Container
from services.bq_client import get_bq_client
import asyncio
import services.generation_service as gen_srv

class GenerationScreen(ControlCenterBaseScreen):
    """Screen for Step 4: Generation Options."""
    
    def __init__(self, state):
        super().__init__(state)
        self.gen_titles = True
        self.gen_desc = True
        
        # Full list of Gemini supported languages
        self.languages = [
            ("Afrikaans (af)", "Afrikaans (af)"),
            ("Albanian (sq)", "Albanian (sq)"),
            ("Amharic (am)", "Amharic (am)"),
            ("Arabic (ar)", "Arabic (ar)"),
            ("Armenian (hy)", "Armenian (hy)"),
            ("Assamese (as)", "Assamese (as)"),
            ("Azerbaijani (az)", "Azerbaijani (az)"),
            ("Basque (eu)", "Basque (eu)"),
            ("Belarusian (be)", "Belarusian (be)"),
            ("Bengali (bn)", "Bengali (bn)"),
            ("Bosnian (bs)", "Bosnian (bs)"),
            ("Bulgarian (bg)", "Bulgarian (bg)"),
            ("Catalan (ca)", "Catalan (ca)"),
            ("Cebuano (ceb)", "Cebuano (ceb)"),
            ("Chinese (Simplified and Traditional) (zh)", "Chinese (Simplified and Traditional) (zh)"),
            ("Corsican (co)", "Corsican (co)"),
            ("Croatian (hr)", "Croatian (hr)"),
            ("Czech (cs)", "Czech (cs)"),
            ("Danish (da)", "Danish (da)"),
            ("Dhivehi (dv)", "Dhivehi (dv)"),
            ("Dutch (nl)", "Dutch (nl)"),
            ("English (en)", "English (en)"),
            ("Esperanto (eo)", "Esperanto (eo)"),
            ("Estonian (et)", "Estonian (et)"),
            ("Filipino (Tagalog) (fil)", "Filipino (Tagalog) (fil)"),
            ("Finnish (fi)", "Finnish (fi)"),
            ("French (fr)", "French (fr)"),
            ("Frisian (fy)", "Frisian (fy)"),
            ("Galician (gl)", "Galician (gl)"),
            ("Georgian (ka)", "Georgian (ka)"),
            ("German (de)", "German (de)"),
            ("Greek (el)", "Greek (el)"),
            ("Gujarati (gu)", "Gujarati (gu)"),
            ("Haitian Creole (ht)", "Haitian Creole (ht)"),
            ("Hausa (ha)", "Hausa (ha)"),
            ("Hawaiian (haw)", "Hawaiian (haw)"),
            ("Hebrew (iw)", "Hebrew (iw)"),
            ("Hindi (hi)", "Hindi (hi)"),
            ("Hmong (hmn)", "Hmong (hmn)"),
            ("Hungarian (hu)", "Hungarian (hu)"),
            ("Icelandic (is)", "Icelandic (is)"),
            ("Igbo (ig)", "Igbo (ig)"),
            ("Indonesian (id)", "Indonesian (id)"),
            ("Irish (ga)", "Irish (ga)"),
            ("Italian (it)", "Italian (it)"),
            ("Japanese (ja)", "Japanese (ja)"),
            ("Javanese (jv)", "Javanese (jv)"),
            ("Kannada (kn)", "Kannada (kn)"),
            ("Kazakh (kk)", "Kazakh (kk)"),
            ("Khmer (km)", "Khmer (km)"),
            ("Korean (ko)", "Korean (ko)"),
            ("Krio (kri)", "Krio (kri)"),
            ("Kurdish (ku)", "Kurdish (ku)"),
            ("Kyrgyz (ky)", "Kyrgyz (ky)"),
            ("Lao (lo)", "Lao (lo)"),
            ("Latin (la)", "Latin (la)"),
            ("Latvian (lv)", "Latvian (lv)"),
            ("Lithuanian (lt)", "Lithuanian (lt)"),
            ("Luxembourgish (lb)", "Luxembourgish (lb)"),
            ("Macedonian (mk)", "Macedonian (mk)"),
            ("Malagasy (mg)", "Malagasy (mg)"),
            ("Malay (ms)", "Malay (ms)"),
            ("Malayalam (ml)", "Malayalam (ml)"),
            ("Maltese (mt)", "Maltese (mt)"),
            ("Maori (mi)", "Maori (mi)"),
            ("Marathi (mr)", "Marathi (mr)"),
            ("Meiteilon (Manipuri) (mni-Mtei)", "Meiteilon (Manipuri) (mni-Mtei)"),
            ("Mongolian (mn)", "Mongolian (mn)"),
            ("Myanmar (Burmese) (my)", "Myanmar (Burmese) (my)"),
            ("Nepali (ne)", "Nepali (ne)"),
            ("Norwegian (no)", "Norwegian (no)"),
            ("Nyanja (Chichewa) (ny)", "Nyanja (Chichewa) (ny)"),
            ("Odia (Oriya) (or)", "Odia (Oriya) (or)"),
            ("Pashto (ps)", "Pashto (ps)"),
            ("Persian (fa)", "Persian (fa)"),
            ("Polish (pl)", "Polish (pl)"),
            ("Portuguese (pt)", "Portuguese (pt)"),
            ("Punjabi (pa)", "Punjabi (pa)"),
            ("Romanian (ro)", "Romanian (ro)"),
            ("Russian (ru)", "Russian (ru)"),
            ("Samoan (sm)", "Samoan (sm)"),
            ("Scots Gaelic (gd)", "Scots Gaelic (gd)"),
            ("Serbian (sr)", "Serbian (sr)"),
            ("Sesotho (st)", "Sesotho (st)"),
            ("Shona (sn)", "Shona (sn)"),
            ("Sindhi (sd)", "Sindhi (sd)"),
            ("Sinhala (Sinhalese) (si)", "Sinhala (Sinhalese) (si)"),
            ("Slovak (sk)", "Slovak (sk)"),
            ("Slovenian (sl)", "Slovenian (sl)"),
            ("Somali (so)", "Somali (so)"),
            ("Spanish (es)", "Spanish (es)"),
            ("Sundanese (su)", "Sundanese (su)"),
            ("Swahili (sw)", "Swahili (sw)"),
            ("Swedish (sv)", "Swedish (sv)"),
            ("Tajik (tg)", "Tajik (tg)"),
            ("Tamil (ta)", "Tamil (ta)"),
            ("Telugu (te)", "Telugu (te)"),
            ("Thai (th)", "Thai (th)"),
            ("Turkish (tr)", "Turkish (tr)"),
            ("Ukrainian (uk)", "Ukrainian (uk)"),
            ("Urdu (ur)", "Urdu (ur)"),
            ("Uyghur (ug)", "Uyghur (ug)"),
            ("Uzbek (uz)", "Uzbek (uz)"),
            ("Vietnamese (vi)", "Vietnamese (vi)"),
            ("Welsh (cy)", "Welsh (cy)"),
            ("Xhosa (xh)", "Xhosa (xh)"),
            ("Yiddish (yi)", "Yiddish (yi)"),
            ("Yoruba (yo)", "Yoruba (yo)"),
            ("Zulu (zu)", "Zulu (zu)")
        ]
        
        self.workers_options = [("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5)]
        
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 4: Generation Options", id="title")
            
            with Container(classes="card"):
                yield Label("Generation Configuration", id="gen-config-title")
                with Horizontal(id="gen-row-1"):
                    with Vertical(classes="col3"):
                        yield Button("[green]✔[/] Generate Titles", id="toggle-titles-btn")
                    with Vertical(classes="col3"):
                        yield Button("[green]✔[/] Generate Descriptions", id="toggle-desc-btn")
                    with Vertical(classes="col3"):
                        yield Label("Language:")
                        default_lang = self.state.get('language', 'English (en)')
                        yield Select(self.languages, value=default_lang, id="language")
                
                with Horizontal(id="gen-row-2"):
                    with Vertical(id="table-col"):
                        yield Label("Destination Table Name:")
                        yield Input(value=self.state.get('output_table', 'Output'), id="output-table")
                    with Vertical(id="workers-col"):
                        yield Label("Workers:")
                        yield Select(self.workers_options, value=self.state.get('workers', 5), id="workers")
            
            with Horizontal():
                yield Button("Run Generation", variant="success", id="run-btn")
                yield Button("Back to Menu", id="back-btn")
                
            yield Label("", id="status-label")
            yield ProgressBar(id="progress-bar")
            
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
        yield Footer()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            lang = self.query_one("#language").value
            workers = int(self.query_one("#workers").value)
            output_table = self.query_one("#output-table").value
            
            self.state.update_data({
                'language': lang,
                'workers': workers,
                'output_table': output_table
            })
            
            self.query_one("#logs-collapsible").collapsed = False
            self.query_one("#progress-bar").styles.display = "block"
            
            debug = getattr(self.state, 'debug', False)
            self.run_worker(lambda: self.run_generation(lang, workers, output_table, self.gen_titles, self.gen_desc, debug), thread=True)
            
        elif event.button.id == "toggle-titles-btn":
            self.gen_titles = not self.gen_titles
            if self.gen_titles:
                event.button.label = "[green]✔[/] Generate Titles"
            else:
                event.button.label = "[red]✘[/] Skip Titles"
                
        elif event.button.id == "toggle-desc-btn":
            self.gen_desc = not self.gen_desc
            if self.gen_desc:
                event.button.label = "[green]✔[/] Generate Descriptions"
            else:
                event.button.label = "[red]✘[/] Skip Descriptions"
                
    def run_generation(self, lang: str, workers: int, output_table: str, gen_titles: bool, gen_desc: bool, debug: bool) -> None:
        self.log_content = ""
        self.write_log("Starting generation process...\n")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        bucket = self.state.get('bucket', f"{project}-images")
        use_images = self.state.get_step_status('images') == 'Completed'
        web_done = self.state.get_step_status('web') == 'Completed'
        
        id_col = self.state.get('id_col', 'id')
        title_col = self.state.get('title_col', 'title')
        desc_col = self.state.get('desc_col', 'description')
        image_col = self.state.get('image_col', 'image_url')
        
        try:
            def progress_cb(total=None, progress=None, step_text=None):
                if step_text is not None:
                    self.app.call_from_thread(self.query_one("#status-label", Label).update, f"[bold]{step_text}[/]")
                if total is not None:
                    self.app.call_from_thread(self.query_one("#progress-bar", ProgressBar).update, total=total, progress=progress)
                elif progress is not None:
                    self.app.call_from_thread(self.query_one("#progress-bar", ProgressBar).update, progress=progress)
                    
            result = gen_srv.run_generation_process(
                project, dataset, lang, workers, output_table, gen_titles, gen_desc, debug, bucket, use_images, web_done,
                id_col, title_col, desc_col, image_col,
                log_cb=self.write_log,
                progress_cb=progress_cb,
                is_cancelled=lambda: self.app._exit
            )
            
            if result.get('cancelled'):
                return
                
            self.state.set_step_status('gen', 'Completed')
            self.app.call_from_thread(self.notify, "Generation completed successfully!", severity="information")
            self.app.call_from_thread(self.query_one("#status-label", Label).update, "[green]Generation completed successfully![/]")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.app.call_from_thread(self.notify, f"Error during generation: {e}", severity="error")
            self.app.call_from_thread(self.query_one("#status-label", Label).update, f"[red]Error during generation: {e}[/]")
