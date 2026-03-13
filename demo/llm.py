from langchain_openai import AzureChatOpenAI

from config import (
    AZURE_API_KEY,
    AZURE_API_VERSION,
    AZURE_DEPLOYMENT,
    AZURE_ENDPOINT,
)


def get_llm():
    return AzureChatOpenAI(
        api_key=AZURE_API_KEY,
        api_version=AZURE_API_VERSION,
        azure_deployment=AZURE_DEPLOYMENT,
        azure_endpoint=AZURE_ENDPOINT,
    )


if __name__ == "__main__":
    llm = get_llm()
    resp = llm.invoke("Say hello in one sentence")
    print(resp.content)
