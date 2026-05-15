from textual.app import ComposeResult
from screens.base_screen import WizardBaseScreen
from textual.widgets import Header, Footer, Input, Button, Label, Collapsible, Static, Log, ProgressBar, Select
from textual.containers import Vertical, Horizontal
from screens.dataset_screen import get_bq_client
import asyncio
import time
import subprocess

class GenerationScreen(WizardBaseScreen):
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
        
        try:
            client = get_bq_client(self.state)
            
            # 1. Prepare Tables
            self.write_log("Preparing tables...\n")
            
            input_proc_id = f"{project}.{dataset}.InputProcessing"
            source_id = f"{project}.{dataset}.InputFiltered"
            web_id = f"{project}.{dataset}.InputFilteredWeb"
            
            web_done = self.state.get_step_status('web') == 'Completed'
            
            if web_done:
                sql_input = f"""
                CREATE OR REPLACE TABLE `{input_proc_id}` AS
                SELECT
                  F.id, F.title, F.description, F.image_url,
                  W.content AS webpage_content
                FROM `{source_id}` AS F
                LEFT JOIN `{web_id}` AS W USING (id);
                """
            else:
                self.write_log("Web scraping was not completed. Skipping join with webpage content.\n")
                sql_input = f"""
                CREATE OR REPLACE TABLE `{input_proc_id}` AS
                SELECT
                  F.id, F.title, F.description, F.image_url,
                  CAST(NULL AS STRING) AS webpage_content
                FROM `{source_id}` AS F;
                """
                
            self.write_log(f"Creating table {input_proc_id}...\n")
            client.query(sql_input).result()
            
            output_id = f"{project}.{dataset}.Output"
            
            sql_output = f"""
            CREATE OR REPLACE TABLE `{output_id}` AS
            SELECT
              id,
              CAST(NULL AS STRING) AS title,
              CAST(NULL AS STRING) AS description,
              0 AS tries,
              CAST(NULL AS TIMESTAMP) AS updated_at,
              CAST(NULL AS STRING) AS raw_response_title,
              CAST(NULL AS STRING) AS raw_response_description
            FROM `{source_id}`;
            """
            
            self.write_log(f"Initializing working table {output_id}...\n")
            client.query(sql_output).result()
            
            self.state.set_step_status('prepare', 'Completed')
            
            # 2. Run Stored Procedures
            targets = []
            if gen_titles: targets.append("Titles")
            if gen_desc: targets.append("Descriptions")
            
            if not targets:
                self.write_log("No targets selected for generation.\n")
                return
                
            bucket = self.state.get('bucket', f"{project}-images")
            use_images = "TRUE" if self.state.get_step_status('images') == 'Completed' else "FALSE"
            
            batch_size = 15
            
            # Get total rows for progress bar
            total_query = f"SELECT COUNT(*) as total FROM `{input_proc_id}`"
            total_rows = list(client.query(total_query).result())[0].total
            
            self.app.call_from_thread(self.state.set, 'gen_count', total_rows)
            
            for target in targets:
                self.write_log(f"\n--- Generating {target} ---\n")
                self.app.call_from_thread(self.query_one("#progress-bar", ProgressBar).update, total=total_rows, progress=0)
                
                procedure = f"BatchedUpdate{target}"
                
                jobs = []
                debug_val = "TRUE" if debug else "FALSE"
                if workers <= 1:
                    sql = f"CALL `{project}.{dataset}`.{procedure}({batch_size}, '{lang}', NULL, NULL, NULL, '{bucket}', {use_images}, {debug_val});"
                    self.write_log(f"Running: {sql}\n")
                    job = client.query(sql)
                    jobs.append(job)
                else:
                    self.write_log(f"Splitting work into {workers} parallel parts...\n")
                    for part in range(workers):
                        sql = f"CALL `{project}.{dataset}`.{procedure}({batch_size}, '{lang}', {workers}, {part}, NULL, '{bucket}', {use_images}, {debug_val});"
                        self.write_log(f"Starting worker {part}/{workers}: {sql}\n")
                        job = client.query(sql)
                        jobs.append(job)
                        
                # Polling for progress
                if target == 'Titles':
                    processed_query = f"SELECT COUNT(*) as processed FROM `{output_id}` WHERE title IS NOT NULL"
                else:
                    processed_query = f"SELECT COUNT(*) as processed FROM `{output_id}` WHERE description IS NOT NULL"
                    
                all_done = False
                while not all_done:
                    all_done = True
                    for job in jobs:
                        job.reload()
                        if not job.done():
                            all_done = False
                            
                    try:
                        processed_rows = list(client.query(processed_query).result())[0].processed
                        self.app.call_from_thread(self.query_one("#progress-bar", ProgressBar).update, progress=processed_rows)
                    except Exception:
                        pass
                        
                    if not all_done:
                        time.sleep(5)
                        
                self.write_log(f"Finished generation for {target}.\n")
                
            # 3. Finalize output table
            if output_table != "Output":
                final_id = f"{project}.{dataset}.{output_table}"
                self.write_log(f"Copying results to final table {final_id}...\n")
                client.query(f"CREATE OR REPLACE TABLE `{final_id}` AS SELECT * FROM `{output_id}`").result()
            
            self.state.set_step_status('gen', 'Completed')
            self.app.call_from_thread(self.notify, "Generation completed successfully!", severity="information")
            self.app.call_from_thread(self.query_one("#status-label", Label).update, "[green]Generation completed successfully![/]")
            
        except Exception as e:
            self.write_log(f"Error: {e}\n")
            self.app.call_from_thread(self.notify, f"Error during generation: {e}", severity="error")
            self.app.call_from_thread(self.query_one("#status-label", Label).update, f"[red]Error during generation: {e}[/]")
