from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential

# Replace with your actual values
SEARCH_SERVICE_NAME = "your-search-service-name"
SEARCH_SERVICE_INDEX = "your-search-index-name"
SEARCH_SERVICE_QUERY_API_KEY = "your-api-key"


def delete_all_documents():
    # Initialize search client
    index_client = SearchClient(
        endpoint=f"https://{SEARCH_SERVICE_NAME}.search.windows.net",
        index_name=SEARCH_SERVICE_INDEX,
        credential=AzureKeyCredential(SEARCH_SERVICE_QUERY_API_KEY),
    )

    try:
        # Query all documents
        search_results = index_client.search(search_text="", select=["id"])
        azure_docs_to_delete = [doc["id"] for doc in search_results]
    except Exception as ex:
        raise Exception("Error during Azure Search query") from ex

    # Delete all documents
    if azure_docs_to_delete:
        try:
            delete_actions = [{"@search.action": "delete", "id": doc_id} for doc_id in azure_docs_to_delete]
            index_client.upload_documents(documents=delete_actions)
        except Exception as ex:
            failed_ids = ", ".join(azure_docs_to_delete)
            raise Exception(f"Failed to delete documents: {failed_ids}") from ex

# Call the function
delete_all_documents()
