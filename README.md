# snyk-projects-tag-updater

 This repository contains a Python script named `snyk_projects_tag_updater.py` that interacts with the Snyk REST API to update project tags. The script retrieves groups, organizations, filtered projects (based on target_runtime = net6.0 and origins = azure-repos), and targets (with pagination and rate limiting). You can choose whether to apply default filtering for projects. If no filter is applied, the script retrieves all projects using only the version parameter. You can also set the tag key (default is Testing) and value (default is DefaultTest); if left blank, the script defaults to these values. The script preserves existing tag data and only updates the specified tag.

## Features

- Retrieves groups, organizations, projects, and targets from Snyk
- Uses pagination and rate limiting (automatic retries on 429 responses)
- Allows optional filtering for projects (default: version = 2024-10-15, limit = 100, target_runtime = net6.0, origins = azure-repos)
- Groups targets by organization and associates projects with their targets
- Displays formatted JSON output, formatted text output, and a summary with counts
- Offers interactive update of project tags using numbered options
- Sends a PATCH request with full project details (attributes and relationships) while updating only the specified tag
- Re-fetches the updated project to confirm that the tag was added and displays a concise log of the change

### Requirements

- Python 3.6 or higher
- [requests](https://pypi.org/project/requests/) library

### Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/1B05H1N/snyk-projects-tag-updater.git
   cd snyk-projects-tag-updater
   ```

2. **Create and activate a virtual environment**

   On macOS/Linux:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   On Windows:

   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install requests
   ```

4. **Set the SNYK_API_TOKEN**

   On macOS/Linux:

   ```bash
   export SNYK_API_TOKEN=your_token_here
   ```

   On Windows:

   ```cmd
   set SNYK_API_TOKEN=your_token_here
   ```

### Usage

Run the script with:

```bash
python snyk_projects_tag_updater.py
```

The script will:

- Retrieve groups, organizations, projects (optionally filtered), and targets from Snyk.
- Display a formatted JSON structure, text output, and a summary on the console.
- Offer options to export the output and summary to TXT and/or JSON files.
- Provide an interactive section to update project tags:
  - You can choose whether to apply default filters to projects.
  - You can select an organization and then specific projects using numbered options, or update all projects.
  - You have the option to specify the tag key (default "Testing") and tag value (default "DefaultTest").
  - The script shows the PATCH request details (URL, headers, and payload) for your review before sending.
  - After sending the PATCH request, it re-fetches the project to confirm that the specified tag was updated and logs the change.
- Display changes made.

### Disclaimer

**Use this script at your own risk.** I am not responsible for any issues, data loss, or damages that may occur as a result of using this script. Please test thoroughly in a safe environment before running it in production.

### License

This project is licensed under the MIT License.
