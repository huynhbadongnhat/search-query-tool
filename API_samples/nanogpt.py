import requests
import json

BASE_URL = "https://nano-gpt.com/api/v1"
API_KEY = "YOUR_API_KEY"  # Replace with your API key

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "text/event-stream"  # Required for SSE streaming
}

def stream_chat_completion(messages, model="chatgpt-4o-latest"):
    """
    Send a streaming chat completion request using the OpenAI-compatible endpoint.
    """
    data = {
        "model": model,
        "messages": messages,
        "stream": True  # Enable streaming
    }

    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=headers,
        json=data,
        stream=True
    )

    if response.status_code != 200:
        raise Exception(f"Error: {response.status_code}")

    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                line = line[6:]
            if line == '[DONE]':
                break
            try:
                chunk = json.loads(line)
                if chunk['choices'][0]['delta'].get('content'):
                    yield chunk['choices'][0]['delta']['content']
            except json.JSONDecodeError:
                continue

# Example usage
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Please explain the concept of artificial intelligence."}
]

try:
    print("Assistant's Response:")
    for content_chunk in stream_chat_completion(messages):
        print(content_chunk, end='', flush=True)
    print("")
except Exception as e:
    print(f"Error: {str(e)}")