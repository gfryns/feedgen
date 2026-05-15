# FeedGen BigQuery Setup Wizard

The **FeedGen BigQuery Setup Wizard** is an interactive, terminal-based User Interface (TUI) designed to automate the deployment and configuration of an e-commerce feed generation pipeline on Google Cloud. 

Using this wizard, digital marketers and data engineers can seamlessly deploy a BigQuery-native infrastructure to enhance product titles and descriptions using Google's Gemini Large Language Models (LLMs).

![Dashboard Preview](https://textual.textualize.io/images/logo.svg) *(Built with [Textual](https://textual.textualize.io/))*

## 🚀 Features

*   **Interactive TUI:** A sleek, keyboard- and mouse-friendly terminal interface with real-time validation, progress bars, and streaming deployment logs.
*   **Infrastructure as Code:** Automatically enables required GCP APIs (Vertex AI), provisions BigQuery Datasets, and creates Cloud Resource Connections with proper IAM role bindings.
*   **BigQuery ML Integration:** Registers Gemini foundation models (e.g., `gemini-2.5-flash`, `gemini-2.5-pro`) directly within BigQuery as remote models.
*   **Data Preparation:** 
    *   Previews raw input tables directly in the terminal.
    *   Provides a visual mapping interface to align your custom schema (ID, Title, Description, Image URL) to the pipeline's expected format.
    *   Supports dynamic SQL filtering.
*   **Data Enrichment (Optional):**
    *   **Web Scraping:** Automatically extracts additional text content from product detail pages using CSS selectors.
    *   **Image Processing:** Downloads product images to Google Cloud Storage (GCS) and registers them as BigQuery External Tables to enable multimodal LLM prompting.
*   **Few-Shot Prompting:** Easily import "Golden Examples" from a Google Sheet or by manually selecting high-performing product IDs to guide the LLM's output style.
*   **Batch Inference:** Deploys highly optimized BigQuery Stored Procedures to run batched, parallelized generation of new titles and descriptions.

## 📁 Project Structure

```text
.
├── src/                    # Application source code
│   ├── app.py              # Main Textual application and Dashboard
│   ├── screens/            # UI components for each wizard step
│   ├── services/           # Decoupled business logic (BigQuery, IAM, Scraping)
│   └── state_manager.py    # Atomic state saving/loading (state.json)
├── tests/                  # Pytest unit tests for business logic
├── prompts/                # Customizable LLM prompt templates (.txt)
├── config.yaml             # Supported GCP Regions and Gemini Models
├── generation.sql          # BigQuery Stored Procedures and Table Schemas
└── requirements.txt        # Python dependencies
```

## 🛠️ Prerequisites

Before running the wizard, ensure you have:
1. Python 3.11+ installed.
2. A Google Cloud Project with billing enabled.
3. Authenticated your local environment with Application Default Credentials (ADC):
   ```bash
   gcloud auth application-default login
   ```
   *(Note: Ensure you include the necessary scopes if importing examples from Google Sheets: `--scopes=https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/cloud-platform`)*

## 📦 Installation

Create a virtual environment and install the required packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 🚦 Usage

Launch the setup wizard from the project root:

```bash
python src/app.py
```

### Debug Mode
If you encounter issues or want to track the application's routing and state changes, launch the app in debug mode. This will generate a `debug_action_log.txt` file in the root directory:

```bash
python src/app.py --debug
```

## 🧪 Testing

The business logic is decoupled from the UI, allowing for fast, mock-based unit testing. The project uses `pytest` and `pytest-mock` to achieve high test coverage.

Run the test suite:
```bash
pytest tests/
```
