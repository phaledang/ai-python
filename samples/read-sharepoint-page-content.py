import requests

# Replace with your actual values
ACCESS_TOKEN = ""
SITE_ID = ""
PAGE_ID = ""

# Microsoft Graph API endpoint
url = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/pages/{PAGE_ID}/microsoft.graph.sitePage?$expand=webParts"

# Set headers for authentication
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept": "application/json"
}

# Make the API request
response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
   
    #print(data)
    # Extract innerHtml and title from webParts
    extracted_content = [
        data.get("title", "") + "\n" + data.get("name", "")
    ]
    for webpart in data.get("webParts", []):
        webpart_inner_html = webpart.get("innerHtml", "")
        extracted_content.append(webpart_inner_html)

    # Merge into a single string
    merged_content = "\n\n".join(filter(None, extracted_content))  # Remove empty values

    # Print output
    print("Merged Content:\n", merged_content)
else:
    print(f"Error: {response.status_code}, {response.text}")
