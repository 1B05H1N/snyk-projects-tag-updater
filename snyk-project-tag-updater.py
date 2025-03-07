import os
import requests
import json
import time

# check for snyk api token
SNYK_API_TOKEN = os.environ.get("SNYK_API_TOKEN")
if not SNYK_API_TOKEN:
    raise Exception("set the snyk_api_token environment variable")

# snyk api version and base url
API_VERSION = "2024-10-15"
BASE_URL = "https://api.snyk.io/rest"

# default pagination parameters
DEFAULT_PAGINATION_PARAMS = {
    "version": API_VERSION,
    "limit": 100
}

# default global headers for snyk api requests (authorization, content-type, accept) 
HEADERS = {
    "Authorization": f"Token {SNYK_API_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/vnd.api+json"
}

# optional filters for projects (target_runtime and origins)
FILTERED_PROJECT_TARGET_RUNTIME = "net6.0"  # set to empty string ("") if you do not want to filter by target runtime
FILTERED_PROJECT_ORIGINS = "azure-repos"    # set to empty string ("") if you do not want to filter by origins

def send_request(method, url, headers=None, max_retries=3, **kwargs):
    """send an http request with rate limit handling"""
    if headers is None:
        headers = HEADERS
    retries = 0
    while True:
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"\nRate limit exceeded. Waiting {retry_after} seconds...\n")
                time.sleep(retry_after)
                retries += 1
                if retries > max_retries:
                    print("Max retries exceeded")
                    response.raise_for_status()
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"\nRequest error on {method} {url}: {e}\n")
            raise e
        
def fetch_all(url, params=None):
    """fetch all paginated results for a given url"""
    results = []
    while url:
        try:
            response = send_request("GET", url, params=params)
            data = response.json()
            results.extend(data.get("data", []))
            next_link = data.get("links", {}).get("next")
            if next_link:
                if next_link.startswith("/rest"):
                    next_link = next_link[len("/rest"):]
                url = BASE_URL + next_link if next_link.startswith("/") else next_link
                params = None
            else:
                url = None
        except Exception as e:
            print("Pagination fetch error:", e)
            break
    return results

def get_groups():
    """retrieve all groups"""
    url = f"{BASE_URL}/groups"
    params = DEFAULT_PAGINATION_PARAMS.copy()
    return fetch_all(url, params)

def get_orgs_for_group(group_id):
    """retrieve organizations for a given group"""
    url = f"{BASE_URL}/groups/{group_id}/orgs"
    params = DEFAULT_PAGINATION_PARAMS.copy()
    return fetch_all(url, params)

def get_filtered_projects(org_id, apply_filter=True):
    """
    retrieve projects optionally filtered by target_runtime and origins.
    always include version and limit.
    """
    url = f"{BASE_URL}/orgs/{org_id}/projects"
    if apply_filter:
        params = {"version": API_VERSION, "limit": 100}
        if FILTERED_PROJECT_TARGET_RUNTIME:
            params["target_runtime"] = FILTERED_PROJECT_TARGET_RUNTIME
        if FILTERED_PROJECT_ORIGINS:
            params["origins"] = FILTERED_PROJECT_ORIGINS
    else:
        params = {"version": API_VERSION, "limit": 100}
    return fetch_all(url, params)

def get_targets_for_org(org_id):
    """retrieve all targets for a given organization"""
    url = f"{BASE_URL}/orgs/{org_id}/targets"
    params = DEFAULT_PAGINATION_PARAMS.copy()
    return fetch_all(url, params)

def get_project_by_id(org_id, project_id):
    """retrieve full project details for a given project id"""
    url = f"{BASE_URL}/orgs/{org_id}/projects/{project_id}"
    params = {"version": API_VERSION}
    try:
        response = send_request("GET", url, params=params)
        return response.json().get("data")
    except Exception as e:
        print(f"Error retrieving project {project_id}: {e}")
        return None

def update_project_tags(org_id, project):
    """
    retrieve full project details and build a patch payload that uses exactly the fields returned
    by get while updating the tags to add or update a tag.
    you have the option to set the tag key (default 'Testing') and tag value (default 'DefaultTest').
    re-fetch the project to confirm the update; return a concise log with org id, project name,
    tag key, and updated tag value.
    """
    project_id = project.get("id")
    full_project = get_project_by_id(org_id, project_id)
    if not full_project:
        return None

    attributes = full_project.get("attributes", {})
    existing_tags = attributes.get("tags", [])
    
    # prompt for tag key and value; default key is 'Testing'
    tag_key = input(f"\nEnter tag key to update (default 'Testing'): ").strip() or "Testing"
    tag_value = input(f"Enter value for tag '{tag_key}' (default 'DefaultTest'): ").strip() or "DefaultTest"
    
    new_tags = existing_tags[:] if existing_tags else []
    found = False
    for i, tag in enumerate(new_tags):
        if tag.get("key") == tag_key:
            new_tags[i]["value"] = tag_value
            found = True
            break
    if not found:
        new_tags.append({"key": tag_key, "value": tag_value})
    
    payload = {
        "data": {
            "attributes": {"tags": new_tags},
            "type": full_project.get("type", "project"),
            "id": full_project.get("id")
        }
    }
    
    relationships = full_project.get("relationships", {})
    if relationships:
        org_rel = relationships.get("organization", {}).get("data", {"id": org_id, "type": "org"})
        org_rel["type"] = "org"
        target_rel = relationships.get("target", {}).get("data")
        if not target_rel:
            print(f"\nProject {project_id} missing target relationship; cannot update\n")
            return None
        target_rel["type"] = "target"
        importer_rel = relationships.get("importer", {}).get("data")
        if not importer_rel:
            print(f"\nProject {project_id} missing importer relationship; cannot update\n")
            return None
        importer_rel["type"] = "user"
        payload["data"]["relationships"] = {
            "organization": {
                "data": org_rel,
                "links": {"related": f"/rest/orgs/{org_rel.get('id')}"}
            },
            "target": {
                "data": target_rel,
                "links": {"related": f"/rest/orgs/{org_id}/targets/{target_rel.get('id')}"}
            },
            "importer": {
                "data": importer_rel,
                "links": {"related": f"/orgs/{org_id}/users/{importer_rel.get('id')}"}
            }
        }
    
    patch_url = f"{BASE_URL}/orgs/{org_id}/projects/{project_id}"
    patch_headers = HEADERS.copy()
    patch_headers["Content-Type"] = "application/vnd.api+json"
    
    # show request details for confirmation
    print("\n--- Patch Request Details ---\n")
    print("URL:", patch_url, "\n")
    print("Headers:\n", json.dumps(patch_headers, indent=2), "\n")
    print("Payload:\n", json.dumps(payload, indent=2), "\n")
    
    if input("Proceed with this PATCH request? (y/n): ").strip().lower() != "y":
        print("\nPatch request cancelled by user\n")
        return None

    try:
        response = send_request("PATCH", patch_url, json=payload, params={"version": API_VERSION}, headers=patch_headers)
        print(f"\nPatch request sent for project {project_id}\n")
        # confirm update by re-fetching the project
        updated_project = get_project_by_id(org_id, project_id)
        updated_tags = updated_project.get("attributes", {}).get("tags", [])
        confirmed = any(tag.get("key") == tag_key and tag.get("value") == tag_value for tag in updated_tags)
        if confirmed:
            project_name = updated_project.get("attributes", {}).get("name", "Unknown")
            log_message = f"Org: {org_id} - Project: {project_name} updated with {tag_key} tag: {tag_value}"
            print("\n" + log_message + "\n")
            return log_message
        else:
            print(f"\nUpdate not confirmed for project {project_id}\n")
            return None
    except Exception as e:
        print(f"\nError updating project {project_id}: {e}\n")
        return None

def build_text_output(result):
    """return a formatted text representation of the data"""
    lines = []
    group = result.get("group", {})
    lines.append(f"Group: {group.get('name', 'Unknown')} (ID: {group.get('id', 'N/A')})\n")
    for org in group.get("orgs", []):
        lines.append(f"  Organization: {org.get('name', 'Unknown')} (ID: {org.get('id', 'N/A')})")
        lines.append(f"    Targets in Org: {len(org.get('targets', []))}\n")
        for proj in org.get("projects", []):
            lines.append(f"    Project: {proj.get('name', 'Unknown')} (ID: {proj.get('id', 'N/A')}, Status: {proj.get('status', 'N/A')}) - Targets: {len(proj.get('targets', []))}")
            if proj.get("targets"):
                for tgt in proj["targets"]:
                    lines.append(f"      Target: {tgt.get('display_name', 'Unknown')} (ID: {tgt.get('id', 'N/A')}, URL: {tgt.get('url', 'N/A')})")
            else:
                lines.append("      Target: None")
            lines.append("")
        lines.append("")
    return "\n".join(lines)

def build_summary_text(result):
    """return a summary with counts and details of changes"""
    lines = []
    group = result.get("group", {})
    orgs = group.get("orgs", [])
    lines.append("Summary:")
    lines.append(f"Total Organizations: {len(orgs)}")
    for org in orgs:
        lines.append("")
        lines.append(f"Organization: {org.get('name', 'Unknown')} (ID: {org.get('id', 'N/A')})")
        lines.append(f"  Total Projects: {len(org.get('projects', []))}")
        lines.append(f"  Total Targets in Org: {len(org.get('targets', []))}")
        for proj in org.get("projects", []):
            lines.append(f"  Project: {proj.get('name', 'Unknown')} (ID: {proj.get('id', 'N/A')}) - Targets: {len(proj.get('targets', []))}")
    return "\n".join(lines)

def main():
    result = {}
    filtered_projects_lookup = {}  # map project_id -> (org_id, project)
    update_logs = []

    groups = get_groups()
    if not groups:
        print("No groups found")
        return

    group = groups[0]
    group_id = group.get("id")
    group_name = group.get("attributes", {}).get("name", "Unknown")
    result["group"] = {"id": group_id, "name": group_name, "orgs": []}

    orgs = get_orgs_for_group(group_id)
    if not orgs:
        print("No organizations found in the group")
        return

    # apply default project filters (target_runtime and origins)
    apply_filter_input = input("\nApply default project filters? (y/n, default y): ").strip().lower() or "y"
    apply_filter = (apply_filter_input == "y")

    for org in orgs:
        org_id = org.get("id")
        org_name = org.get("attributes", {}).get("name", "Unknown")
        org_entry = {"id": org_id, "name": org_name, "projects": []}

        targets = get_targets_for_org(org_id)
        target_dict = {}
        for t in targets:
            try:
                t_id = t.get("id")
                target_dict[t_id] = {
                    "id": t_id,
                    "display_name": t.get("attributes", {}).get("display_name", "N/A"),
                    "url": t.get("attributes", {}).get("url", "N/A")
                }
            except Exception as e:
                print(f"Error processing target: {e}")
        org_entry["targets"] = list(target_dict.values())

        projects = get_filtered_projects(org_id, apply_filter)
        if projects:
            for project in projects:
                proj_id = project.get("id")
                proj_name = project.get("attributes", {}).get("name", "Unknown")
                proj_status = project.get("attributes", {}).get("status", "Unknown")
                proj_entry = {
                    "id": proj_id,
                    "name": proj_name,
                    "status": proj_status,
                    "targets": []
                }
                rel = project.get("relationships", {})
                target_data = []
                if "targets" in rel:
                    target_data = rel["targets"].get("data", [])
                elif "target" in rel:
                    td = rel["target"].get("data")
                    if isinstance(td, list):
                        target_data = td
                    elif td:
                        target_data = [td]
                for t in target_data:
                    t_id = t.get("id")
                    if t_id in target_dict:
                        proj_entry["targets"].append(target_dict[t_id])
                    else:
                        proj_entry["targets"].append({
                            "id": t_id,
                            "display_name": "Not found",
                            "url": ""
                        })
                org_entry["projects"].append(proj_entry)
                filtered_projects_lookup[proj_id] = (org_id, project)
        result["group"]["orgs"].append(org_entry)

    print("\nFinal JSON structure:\n")
    print(json.dumps(result, indent=2))
    print("\n" + "=" * 60 + "\n")
    
    text_output = build_text_output(result)
    print("Well formatted output:\n")
    print(text_output)
    print("\n" + "=" * 60 + "\n")
    
    summary_text = build_summary_text(result)
    print("Summary:\n")
    print(summary_text)
    print("\n" + "=" * 60 + "\n")
    
    try:
        file_choice = input("Write output to file? (y/n): ").strip().lower()
    except Exception:
        file_choice = "n"
    if file_choice == "y":
        fmt_choice = input("Which format? (txt/json/both): ").strip().lower()
        if fmt_choice in ("txt", "both"):
            txt_filename = input("Enter TXT filename (default: output.txt): ").strip() or "output.txt"
            try:
                with open(txt_filename, "w") as f:
                    f.write(text_output + "\n")
                print(f"\nTXT output written to {txt_filename}\n")
            except Exception as e:
                print("Error writing TXT file:", e)
        if fmt_choice in ("json", "both"):
            json_filename = input("Enter JSON filename (default: output.json): ").strip() or "output.json"
            try:
                with open(json_filename, "w") as f:
                    json.dump(result, f, indent=2)
                print(f"\nJSON output written to {json_filename}\n")
            except Exception as e:
                print("Error writing JSON file:", e)
    try:
        summary_choice = input("Write summary to file? (y/n): ").strip().lower()
    except Exception:
        summary_choice = "n"
    if summary_choice == "y":
        summary_filename = input("Enter summary filename (default: summary.txt): ").strip() or "summary.txt"
        try:
            with open(summary_filename, "w") as f:
                f.write(summary_text + "\n")
            print(f"\nSummary written to {summary_filename}\n")
        except Exception as e:
            print("Error writing summary file:", e)
    
    # interactive tag updater
    print("\nInteractive Tag Update")
    print("-----------------------\n")
    proj_numbers = {}
    for idx, (pid, (org_id, proj)) in enumerate(filtered_projects_lookup.items(), start=1):
        proj_name = proj.get("attributes", {}).get("name", "Unknown")
        proj_numbers[idx] = pid
        print(f"{idx}: {pid} : {proj_name}")
    
    update_choice = input("\nUpdate tags for filtered projects? (y/n): ").strip().lower()
    if update_choice == "y":
        all_update = input("Update ALL filtered projects? (y/n): ").strip().lower()
        if all_update == "y":
            projects_to_update = list(filtered_projects_lookup.keys())
        else:
            orgs_with_projects = [org for org in result["group"]["orgs"] if org.get("projects")]
            if not orgs_with_projects:
                print("No organizations with filtered projects available")
                projects_to_update = []
            else:
                print("\nSelect an organization by number:")
                org_numbers = {}
                for i, org in enumerate(orgs_with_projects, start=1):
                    org_numbers[i] = org["id"]
                    print(f"{i}: {org['name']} (ID: {org['id']})")
                try:
                    org_sel = int(input("Enter organization number: ").strip())
                    if org_sel not in org_numbers:
                        print("Invalid organization number")
                        projects_to_update = []
                    else:
                        selected_org_id = org_numbers[org_sel]
                        org_projects = [(pid, proj) for pid, (oid, proj) in filtered_projects_lookup.items() if oid == selected_org_id]
                        if not org_projects:
                            print("No projects in selected organization")
                            projects_to_update = []
                        else:
                            print("\nSelect projects to update by number (comma separated) or type 'all':")
                            for j, (pid, proj) in enumerate(org_projects, start=1):
                                proj_name = proj.get("attributes", {}).get("name", "Unknown")
                                print(f"{j}: {pid} : {proj_name}")
                            proj_sel = input("Enter your selection: ").strip().lower()
                            if proj_sel == "all":
                                projects_to_update = [pid for pid, _ in org_projects]
                            else:
                                selected_numbers = [int(x.strip()) for x in proj_sel.split(",") if x.strip().isdigit()]
                                projects_to_update = []
                                for num in selected_numbers:
                                    if num < 1 or num > len(org_projects):
                                        print(f"Project number {num} is out of range")
                                    else:
                                        projects_to_update.append(org_projects[num-1][0])
                except Exception as e:
                    print("Invalid input:", e)
                    projects_to_update = []
        if not projects_to_update:
            print("\nNo valid project IDs selected. Exiting update section.\n")
        else:
            for pid in projects_to_update:
                org_id, proj = filtered_projects_lookup[pid]
                log_entry = update_project_tags(org_id, proj)
                if log_entry:
                    update_logs.append(log_entry)
                time.sleep(1)  # rate limit delay 
    else:
        print("\nNo projects were updated.\n")
    
    if update_logs:
        print("\nChanges Made:")
        for log in update_logs:
            print(log)
    else:
        print("\nNo changes were made.\n")
    
    print("\nScript completed.\n")

if __name__ == "__main__":
    main()