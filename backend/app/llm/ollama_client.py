import requests


def generate_answer(prompt: str) -> str:
    response = requests.post(
        "http://host.docker.internal:11434/api/generate",
        json={
            "model": "llama3.2",
            "prompt": prompt,
            "stream": False,
        },
        timeout=90,
    )

    response.raise_for_status()
    return response.json()["response"]