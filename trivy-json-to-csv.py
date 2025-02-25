import json
import pandas as pd
import os

# Load JSON file
with open("trivy_output.json", "r") as file:
    data = json.load(file)

# Ensure the output directory exists
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

# Process each target (Library/File scanned)
for result in data.get("Results", []):
    target_name = result.get("Target", "unknown_target").replace("/", "_").replace(":", "_")
    output_file = os.path.join(output_dir, f"{target_name}.csv")

    # Extract vulnerabilities for this target
    records = []
    for vuln in result.get("Vulnerabilities", []):
        flattened_vuln = {"Target": target_name}
        flattened_vuln.update(vuln)  # Merge all vulnerability fields
        records.append(flattened_vuln)

    # Convert to DataFrame and save to CSV
    if records:
        df = pd.DataFrame(records)
        df.to_csv(output_file, index=False)
        print(f"CSV file saved: {output_file}")
    else:
        print(f"No vulnerabilities found for {target_name}, skipping file creation.")

print("All CSV files have been generated under 'output/' folder.")
