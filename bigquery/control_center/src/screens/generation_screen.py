from textual.app import ComposeResult
from screens.base_screen import ControlCenterBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, ProgressBar, Select
from textual.containers import Vertical, Horizontal, Container
from services.bq_client import get_bq_client
import services.generation_service as gen_srv

class GenerationScreen(ControlCenterBaseScreen):
    """Screen for Step 4: Generation Options."""
    
    def __init__(self, state):
        super().__init__(state)
        self.gen_titles = True
        self.gen_desc = True
        self.gen_highlights = True
        
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
        
        try:
            import yaml
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                self.models = [(m['label'], m['value']) for m in config.get('models', [])]
        except Exception:
            self.models = [("Gemini 2.5 Flash", "gemini-2.5-flash")]
            
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form-container"):
            yield Label("Step 4: Generation Options", id="title")
            
            with Container(classes="card"):
                yield Label("Generation Configuration", id="gen-config-title")
                
                saved_model = self.state.get('model', 'gemini-2.5-flash')
                model_options = [m[1] for m in self.models]
                
                if saved_model in model_options:
                    select_value = saved_model
                    custom_value = ""
                else:
                    select_value = "other"
                    custom_value = saved_model
                    
                default_lang = self.state.get('language', 'English (en)')

                with Horizontal(id="gen-row-1"):
                    with Vertical(classes="col3"):
                        yield Button("[green]✔[/] Generate Titles", id="toggle-titles-btn")
                    with Vertical(classes="col3"):
                        yield Button("[green]✔[/] Generate Descriptions", id="toggle-desc-btn")
                    with Vertical(classes="col3"):
                        yield Button("[green]✔[/] Generate Highlights", id="toggle-highlights-btn")
                        
                with Horizontal(id="gen-row-2"):
                    with Vertical(classes="col"):
                        yield Label("Gemini Model Version:")
                        yield Select(self.models, value=select_value, id="model")
                    with Vertical(classes="col"):
                        yield Label("Language:")
                        yield Select(self.languages, value=default_lang, id="language")
                        
                with Horizontal(id="gen-row-3"):
                    with Vertical(classes="col"):
                        yield Label("Destination Table Name:")
                        yield Input(value=self.state.get('output_table', 'Output'), id="output-table")
                    with Vertical(classes="col"):
                        yield Input(value=custom_value, placeholder="Enter custom model ID", id="custom-model")
            
            with Horizontal():
                yield Button("Run Generation", variant="success", id="run-btn")
                yield Button("Stop Batch Prediction", variant="error", id="cancel-btn", disabled=True)
                yield Button("Cancel", id="back-btn")
                
            yield Label("", id="status-label")
            
            yield Label("Titles: Not started", id="titles-job-label", classes="job-label")
            yield Label("Descriptions: Not started", id="descriptions-job-label", classes="job-label")
            yield Label("Highlights: Not started", id="highlights-job-label", classes="job-label")
            
            with Collapsible(title="Logs", id="logs-collapsible", collapsed=True):
                yield Log(id="process-logs")
                yield Button("Copy Logs to Clipboard", id="copy-logs-btn")
        yield Footer()
        
    def on_mount(self) -> None:
        saved_model = self.state.get('model', 'gemini-2.5-flash')
        model_options = [m[1] for m in self.models]
        
        if saved_model not in model_options:
            self.query_one("#custom-model").styles.display = "block"
        else:
            self.query_one("#custom-model").styles.display = "none"
            
        # Auto-resume if triggered from app start
        if self.state.get('auto_resume'):
            self.state.set('auto_resume', False, save=False)
            self.run_resume()
            
    def on_resume_decision(self, resume: bool) -> None:
        if resume:
            self.run_resume()
        else:
            from services.generation_service import update_ongoing_state
            update_ongoing_state(clear=True)
            
    def run_resume(self) -> None:
        ongoing = self.state.get('ongoing_generation')
        if not ongoing:
            return
            
        job_ids = ongoing.get('job_ids', {})
        
        # Enable cancel button for resumed jobs
        self.query_one("#cancel-btn", Button).disabled = False
        self.app.is_cancelled = False
        
        def progress_cb(target=None, state=None, start_time=None, step_text=None, success_count=0, failed_count=0, total=0):
            if step_text is not None:
                self.app.call_from_thread(self.query_one("#status-label", Label).update, f"[bold]{step_text}[/]")
            if target is not None:
                label_id = f"#{target.lower()}-job-label"
                text = f"{target}: {state}"
                if state not in ["JOB_STATE_CANCELLED", "CANCELLED", "STOPPED"]:
                    if total > 0:
                        completed = success_count + failed_count
                        text += f" ({completed}/{total} completed)"
                        if failed_count > 0:
                            text += f" [{failed_count} failed]"
                    if start_time:
                        text += f" (Started: {start_time})"
                    import time
                    current_time = time.strftime("%H:%M:%S")
                    text += f" [dim](Last checked: {current_time})[/dim]"
                self.app.call_from_thread(self.show_job_label, label_id, text)
                if state in ["JOB_STATE_CANCELLED", "CANCELLED", "STOPPED", "JOB_STATE_SUCCEEDED", "SUCCEEDED"]:
                    self.app.call_from_thread(self.set_timer, 15, lambda: self.hide_job_label(label_id))
                
        def run_resume_thread():
            project = self.state.get('project')
            dataset = self.state.get('dataset')
            bucket = self.state.get('bucket')
            output_table = self.state.get('output_table')
            
            try:
                import services.generation_service as gen_srv
                result = gen_srv.resume_generation_process(
                    project, dataset, bucket, output_table,
                    job_ids,
                    log_cb=self.write_log,
                    progress_cb=progress_cb,
                    is_cancelled=lambda: getattr(self.app, 'is_cancelled', False)
                )
                
                if result.get('cancelled'):
                    self.app.call_from_thread(self.query_one("#status-label", Label).update, "[#E69F00]Jobs cancelled by user.[/]")
                    self.app.call_from_thread(self.disable_cancel_button)
                    return
                    
                self.state.set_step_status('gen', 'Completed')
                self.app.call_from_thread(self.disable_cancel_button)
                self.app.call_from_thread(self.notify, "Generation completed successfully!", severity="information")
                self.app.call_from_thread(self.query_one("#status-label", Label).update, "[green]Generation completed successfully![/]")
                
            except Exception as e:
                self.write_log(f"Error in resume: {e}\n")
                self.app.call_from_thread(self.notify, f"Error: {e}", severity="error")
                self.app.call_from_thread(self.disable_cancel_button)
                self.app.call_from_thread(self.query_one("#status-label", Label).update, f"[red]Error: {e}[/]")
                
        import threading
        threading.Thread(target=run_resume_thread, daemon=True).start()
            

            
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "model":
            if event.value == "other":
                self.query_one("#custom-model").styles.display = "block"
            else:
                self.query_one("#custom-model").styles.display = "none"
                
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self.query_one("#cancel-btn", Button).disabled = False
            self.app.is_cancelled = False
            lang = self.query_one("#language").value
            output_table = self.query_one("#output-table").value
            
            model_val = self.query_one("#model").value
            if model_val == "other":
                model_val = self.query_one("#custom-model").value
                if not model_val:
                    self.notify("Custom model ID is required!", severity="error")
                    return
                    
            self.state.update_data({
                'language': lang,
                'output_table': output_table,
                'model': model_val
            })
            
            
            debug = getattr(self.state, 'debug', False)
            self.run_worker(lambda: self.run_generation(lang, output_table, self.gen_titles, self.gen_desc, self.gen_highlights, debug, model_val), thread=True)
            
        elif event.button.id == "cancel-btn":
            self.app.is_cancelled = True
            self.notify("Cancellation requested...", severity="warning")
            event.button.disabled = True
            
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
                
        elif event.button.id == "toggle-highlights-btn":
            self.gen_highlights = not self.gen_highlights
            if self.gen_highlights:
                event.button.label = "[green]✔[/] Generate Highlights"
            else:
                event.button.label = "[red]✘[/] Skip Highlights"

    def show_job_label(self, label_id: str, text: str):
        label = self.query_one(label_id, Label)
        label.update(text)
        label.styles.display = "block"
        
    def hide_job_label(self, label_id: str):
        try:
            label = self.query_one(label_id, Label)
            label.styles.display = "none"
        except Exception: pass
        
    def disable_cancel_button(self):
        try:
            self.query_one("#cancel-btn", Button).disabled = True
        except Exception: pass
        

                
    def run_generation(self, lang: str, output_table: str, gen_titles: bool, gen_desc: bool, gen_highlights: bool, debug: bool, model_val: str) -> None:
        self.log_content = ""
        self.write_log("Starting generation process...\n")
        
        project = self.state.get('project')
        dataset = self.state.get('dataset')
        region_val = self.state.get('region', 'EU')
        
        # Read bucket from state (configured in Setup Screen)
        bucket = self.state.get('bucket')
        if not bucket:
            # Fallback to config or default
            bucket = f"{project}-feedgen"
            try:
                import yaml
                with open('config.yaml', 'r') as f:
                    config = yaml.safe_load(f)
                    buckets_config = config.get('buckets', {})
                    if buckets_config.get('name'):
                        bucket = buckets_config.get('name').replace("${project}", project)
            except Exception:
                pass
                
        images_bucket = bucket
        output_bucket = bucket
        use_images = self.state.get_step_status('images') == 'Completed'
        web_done = self.state.get_step_status('web') == 'Completed'
        
        id_col = self.state.get('id_col', 'id')
        title_col = self.state.get('title_col', 'title')
        desc_col = self.state.get('desc_col', 'description')
        image_col = self.state.get('image_col', 'image_url')
        
        try:
            def progress_cb(target=None, state=None, start_time=None, step_text=None, success_count=0, failed_count=0, total=0):
                if step_text is not None:
                    self.app.call_from_thread(self.query_one("#status-label", Label).update, f"[bold]{step_text}[/]")
                if target is not None:
                    label_id = f"#{target.lower()}-job-label"
                    text = f"{target}: {state}"
                    if state not in ["JOB_STATE_CANCELLED", "CANCELLED", "STOPPED"]:
                        if total > 0:
                            completed = success_count + failed_count
                            text += f" ({completed}/{total} completed)"
                            if failed_count > 0:
                                text += f" [{failed_count} failed]"
                        if start_time:
                            text += f" (Started: {start_time})"
                        import time
                        current_time = time.strftime("%H:%M:%S")
                        text += f" [dim](Last checked: {current_time})[/dim]"
                    self.app.call_from_thread(self.show_job_label, label_id, text)
                    if state in ["JOB_STATE_CANCELLED", "CANCELLED", "STOPPED", "JOB_STATE_SUCCEEDED", "SUCCEEDED"]:
                        self.app.call_from_thread(self.set_timer, 15, lambda: self.hide_job_label(label_id))
                    
            result = gen_srv.run_generation_process(
                project, dataset, lang, output_table, gen_titles, gen_desc, debug, images_bucket, use_images, web_done,
                id_col, title_col, desc_col, image_col,
                output_bucket=output_bucket,
                region_val=region_val,
                model_val=model_val,
                log_cb=self.write_log,
                progress_cb=progress_cb,
                is_cancelled=lambda: getattr(self.app, 'is_cancelled', False),
                gen_highlights=gen_highlights
            )
            
            if result.get('cancelled'):
                self.app.call_from_thread(self.query_one("#status-label", Label).update, "[#E69F00]Jobs cancelled by user.[/]")
                self.app.call_from_thread(self.disable_cancel_button)
                return
                
            self.state.set_step_status('gen', 'Completed')
            self.app.call_from_thread(self.disable_cancel_button)
            self.app.call_from_thread(self.notify, "Generation completed successfully!", severity="information")
            self.app.call_from_thread(self.query_one("#status-label", Label).update, "[green]Generation completed successfully![/]")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.app.call_from_thread(self.notify, f"Error during generation: {e}", severity="error")
            self.app.call_from_thread(self.disable_cancel_button)
            self.app.call_from_thread(self.query_one("#status-label", Label).update, f"[red]Error during generation: {e}[/]")
