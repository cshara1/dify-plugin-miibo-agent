import requests
from typing import Any, Optional, Union
from dify_plugin.entities.model.message import PromptMessageTool

class MiiboAgent:
    def __init__(self, agent_id: str, api_key: str):
        self.agent_id = agent_id
        self.api_key = api_key

    def _build_messages(self, messages: list[dict]) -> str:
        if len(messages) == 0:
            return ""
        user_messages = [msg["content"] for msg in messages if msg["role"] == "user"]
        return user_messages[-1]

    def generate(
        self,
        model: str,
        stream: bool,
        messages: list[dict],
        parameters: dict[str, Any],
        timeout: int,
        user: str,
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> dict:
        full_request = {
            "api_key": self.api_key,
            "agent_id": self.agent_id,
            "utterance": self._build_messages(messages),
            "uid": user,
        }

        try:
            response = requests.post(
                "https://api-mebo.dev/api",
                json=full_request,
                timeout=timeout,
                stream=stream,
                headers= {
                    "accept": "application/json",
                    "content-type": "application/json"
                }
            )
        except requests.exceptions.RequestException as error:
            raise Exception(f"Failed to invoke model: {e}")



        if response.status_code != 200:
            try:
                resp = response.json()
                # try to parse error message
                err = resp["error"]["type"]
                msg = resp["error"]["message"]
            except Exception as e:
                raise Exception(f"Failed to convert response to json: {e} with text: {response.text}")
            
        if stream:
            return response.iter_lines()
        else:
            return response.json()


    def handle_error(self, error: Exception) -> None:
        print(str(error) if isinstance(error, Exception) else "Unexpected Error")

